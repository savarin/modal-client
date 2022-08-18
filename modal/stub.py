import asyncio
import inspect
import os
import sys
from typing import Collection, Dict, Optional, Union

from rich.tree import Tree

from modal_proto import api_pb2
from modal_utils.app_utils import is_valid_app_name
from modal_utils.async_utils import TaskContext, synchronize_apis, synchronizer
from modal_utils.decorator_utils import decorator_with_options

from ._function_utils import FunctionInfo
from ._output import OutputManager, step_completed, step_progress
from .app import _App, container_app, is_local
from .client import _Client
from .config import config, logger
from .exception import InvalidError
from .functions import _Function
from .image import _DebianSlim, _Image
from .mount import _create_client_mount, _Mount, client_mount_name
from .object import Object, Ref, ref
from .rate_limit import RateLimit
from .schedule import Schedule
from .secret import _Secret
from .shared_volume import _SharedVolume


class _Stub:
    """A `Stub` is a description of how to create a Modal application.

    The stub object principally describes Modal objects (`Function`, `Image`,
    `Secret`, etc.) associated with the application. It has three responsibilities:

    * Syncing of identities across processes (your local Python interpreter and
      every Modal worker active in your application).
    * Making Objects stay alive and not be garbage collected for as long as the
      app lives (see App lifetime below).
    * Manage log collection for everything that happens inside your code.

    **Registering functions with an app**

    The most common way to explicitly register an Object with an app is through the
    `@stub.function` decorator. It both registers the annotated function itself and
    other passed objects, like schedules and secrets, with the app:

    ```python
    import modal

    stub = modal.Stub()

    @stub.function(
        secret=modal.ref("some_secret"),
        schedule=modal.Period(days=1),
    )
    def foo():
        pass
    ```

    In this example, the secret and schedule are registered with the app.
    """

    _name: str
    _description: str
    _blueprint: Dict[str, Object]
    _default_image: _Image
    _client_mount: Optional[Union[_Mount, Ref]]
    _function_mounts: Dict[str, _Mount]
    _mounts: Collection[Union[_Mount, Ref]]

    def __init__(self, name: str = None, *, mounts: Collection[Union[_Mount, Ref]] = [], **blueprint) -> None:
        """Construct a new app stub, optionally with default mounts."""

        self._name = name
        if name is not None:
            self._description = name
        else:
            self._description = self._infer_app_desc()
        self._blueprint = blueprint
        self._default_image = _DebianSlim()
        self._client_mount = None
        self._function_mounts = {}
        self._mounts = mounts
        super().__init__()

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._description

    def _infer_app_desc(self):
        script_filename = os.path.split(sys.argv[0])[-1]
        args = [script_filename] + sys.argv[1:]
        return " ".join(args)

    def __getitem__(self, tag: str):
        # Deprecated?
        return ref(None, tag)

    def __setitem__(self, tag: str, obj: Object):
        # Deprecated ?
        self._blueprint[tag] = obj

    def __getattr__(self, tag: str) -> Ref:
        assert isinstance(tag, str)
        # Return a reference to an object that will be created in the future
        return ref(None, tag)

    def __setattr__(self, tag: str, obj: Object):
        # Note that only attributes defined in __annotations__ are set on the object itself,
        # everything else is registered on the blueprint
        if tag in self.__annotations__:
            object.__setattr__(self, tag, obj)
        else:
            self._blueprint[tag] = obj

    def is_inside(self, image: Optional[Ref] = None) -> bool:
        """Returns if the program is currently running inside a container for this app."""
        # TODO(erikbern): Add a client test for this function.
        if image is not None and not isinstance(image, Ref):
            raise InvalidError(
                inspect.cleandoc(
                    """`is_inside` only works for an image associated with an App. For instance:
                stub.image = DebianSlim()
                if stub.is_inside(stub.image):
                    print("I'm inside!")"""
                )
            )

        if is_local():  # TODO: this should just be a global function
            return False
        if image is None:
            if "image" in self._blueprint:
                image = ref(None, "image")
            else:
                return container_app._is_inside(self._default_image)
        return container_app._is_inside(image)

    @synchronizer.asynccontextmanager
    async def _run(
        self,
        client,
        output_mgr: OutputManager,
        existing_app_id: Optional[str],
        last_log_entry_id: Optional[str] = None,
        description: Optional[str] = None,
        deployment: bool = False,
    ):
        if existing_app_id is not None:
            app = await _App.init_existing(self, client, existing_app_id)
        else:
            app = await _App.init_new(self, client, description if description is not None else self.description)

        # Start tracking logs and yield context
        async with TaskContext(grace=config["logs_timeout"]) as tc:
            with output_mgr.ctx_if_visible(output_mgr.make_live(step_progress("Initializing..."))):
                live_task_status = output_mgr.make_live(step_progress("Running app..."))
                app_id = app.app_id
                logs_loop = tc.create_task(
                    output_mgr.get_logs_loop(app_id, client, live_task_status, last_log_entry_id or "")
                )
            output_mgr.print_if_visible(step_completed("Initialized."))

            try:
                # Create all members
                progress = Tree(step_progress("Creating objects..."), guide_style="gray50")
                with output_mgr.ctx_if_visible(output_mgr.make_live(progress)):
                    await app.create_all_objects(progress)
                progress.label = step_completed("Created objects.")
                output_mgr.print_if_visible(progress)

                # Cancel logs loop after creating objects for a deployment.
                # TODO: we can get rid of this once we have 1) a way to separate builder
                # logs from runner logs and 2) a termination signal that's sent after object
                # creation is complete, that is also triggered on exceptions (`app.disconnect()`)
                if deployment:
                    logs_loop.cancel()

                # Yield to context
                with output_mgr.ctx_if_visible(live_task_status):
                    yield app
            except KeyboardInterrupt:
                print(
                    "Disconnecting from Modal - This will terminate your Modal app in a few seconds.\n"
                    "Stick around for remote tracebacks..."
                )
            finally:
                await app.disconnect()

        if deployment:
            output_mgr.print_if_visible(step_completed("App deployed! 🎉"))
        else:
            output_mgr.print_if_visible(step_completed("App completed."))

    @synchronizer.asynccontextmanager
    async def run(self, client=None, stdout=None, show_progress=None):
        """Context manager that runs an app on Modal.

        Use this as the main entry point for your Modal application. All calls
        to Modal functions should be made within the scope of this context
        manager, and they will correspond to the current app.

        See the documentation for the [`App`](modal.App) class for more details.
        """
        if not is_local():
            raise InvalidError(
                "Can not run an app from within a container. You might need to do something like this: \n"
                'if __name__ == "__main__":\n'
                "    with stub.run():\n"
                "        ...\n"
            )
        if client is None:
            client = await _Client.from_env()
        output_mgr = OutputManager(stdout, show_progress)
        async with self._run(client, output_mgr, None) as app:
            yield app

    async def run_forever(self, client=None, stdout=None, show_progress=None) -> None:
        """Run an app until the program is interrupted.

        This function is useful for testing schedules and webhooks, since they
        will run at a regular cadence until the program is interrupted with
        `Ctrl + C` or other means.
        """
        if not is_local():
            raise InvalidError(
                "Can not run an app from within a container. You might need to do something like this: \n"
                'if __name__ == "__main__":\n'
                "    with stub.run_forever():\n"
                "        ...\n"
            )
        if client is None:
            client = await _Client.from_env()
        output_mgr = OutputManager(stdout, show_progress)
        async with self._run(client, output_mgr, None):
            timeout = config["run_forever_timeout"]
            if timeout:
                output_mgr.print_if_visible(step_completed(f"Running for {timeout} seconds... hit Ctrl-C to stop!"))
                await asyncio.sleep(timeout)
            else:
                output_mgr.print_if_visible(step_completed("Running forever... hit Ctrl-C to stop!"))
                while True:
                    await asyncio.sleep(1.0)

    async def deploy(
        self,
        name: str = None,  # Unique name of the deployment. Subsequent deploys with the same name overwrites previous ones. Falls back to the app name
        namespace=api_pb2.DEPLOYMENT_NAMESPACE_ACCOUNT,
        client=None,
        stdout=None,
        show_progress=None,
    ):
        """Deploy an app and export its objects persistently.

        Typically, using the command-line tool `modal app deploy <module or script>`
        should be used, instead of this method.

        **Usage:**

        ```python
        if __name__ == "__main__":
            stub.deploy()
        ```

        Deployment has two primary purposes:

        * Persists all of the objects in the app, allowing them to live past the
          current app run. For schedules this enables headless "cron"-like
          functionality where scheduled functions continue to be invoked after
          the client has disconnected.
        * Allows for certain kinds of these objects, _deployment objects_, to be
          referred to and used by other apps.
        """
        if not is_local():
            raise InvalidError("Can not run an deploy from within a container.")
        if name is None:
            name = self.name
        if name is None:
            raise InvalidError(
                "You need to either supply an explicit deployment name to the deploy command, or have a name set on the app.\n"
                "\n"
                "Examples:\n"
                'stub.deploy("some_name")\n\n'
                "or\n"
                'stub = Stub("some-name")'
            )

        if not is_valid_app_name(name):
            raise InvalidError(
                f"Invalid app name {name}. App names may only contain alphanumeric characters, dashes, periods, and underscores, and must be less than 64 characters in length. "
            )

        if client is None:
            client = await _Client.from_env()

        # Look up any existing deployment
        app_req = api_pb2.AppGetByDeploymentNameRequest(name=name, namespace=namespace, client_id=client.client_id)
        app_resp = await client.stub.AppGetByDeploymentName(app_req)
        existing_app_id = app_resp.app_id or None
        last_log_entry_id = app_resp.last_log_entry_id

        # The `_run` method contains the logic for starting and running an app
        output_mgr = OutputManager(stdout, show_progress)
        async with self._run(
            client, output_mgr, existing_app_id, last_log_entry_id, description=name, deployment=True
        ) as app:
            deploy_req = api_pb2.AppDeployRequest(
                app_id=app._app_id,
                name=name,
                namespace=namespace,
            )
            await client.stub.AppDeploy(deploy_req)
            return app._app_id

    def _get_default_image(self):
        if "image" in self._blueprint:
            return self._blueprint["image"]
        else:
            return self._default_image

    def _get_function_mounts(self, raw_f):
        # Get the common mounts for the stub.
        mounts = list(self._mounts)

        # Create client mount
        if self._client_mount is None:
            if config["sync_entrypoint"]:
                self._client_mount = _create_client_mount()
            else:
                self._client_mount = ref(client_mount_name(), namespace=api_pb2.DEPLOYMENT_NAMESPACE_GLOBAL)
        mounts.append(self._client_mount)

        # Create function mounts
        info = FunctionInfo(raw_f)
        for key, mount in info.get_mounts().items():
            if key not in self._function_mounts:
                self._function_mounts[key] = mount
            mounts.append(self._function_mounts[key])

        return mounts

    def _add_function(self, function):
        if function.tag in self._blueprint:
            old_function = self._blueprint[function.tag]
            if isinstance(old_function, _Function):
                logger.warning(
                    f"Warning: Tag {function.tag} collision!"
                    f" Overriding existing function [{old_function._info.module_name}].{old_function._info.function_name}"
                    f" with new function [{function._info.module_name}].{function._info.function_name}"
                )
            else:
                logger.warning(f"Warning: tag {function.tag} exists but is overriden by function")
        self._blueprint[function.tag] = function
        return function

    @decorator_with_options
    def function(
        self,
        raw_f=None,  # The decorated function
        *,
        image: Union[_Image, Ref] = None,  # The image to run as the container for the function
        schedule: Optional[Schedule] = None,  # An optional Modal Schedule for the function
        secret: Optional[
            Union[_Secret, Ref]
        ] = None,  # An optional Modal Secret with environment variables for the container
        secrets: Collection[Union[_Secret, Ref]] = (),  # Plural version of `secret` when multiple secrets are needed
        gpu: bool = False,  # Whether a GPU is required
        rate_limit: Optional[RateLimit] = None,  # Optional RateLimit for the function
        serialized: bool = False,  # Whether to send the function over using cloudpickle.
        mounts: Collection[Union[_Mount, Ref]] = (),
        shared_volumes: Dict[str, Union[_SharedVolume, Ref]] = {},
        memory: Optional[int] = None,  # How much memory to request, in MB. This is a soft limit.
        proxy: Optional[Ref] = None,  # Reference to a Modal Proxy to use in front of this function.
        retries: Optional[int] = None,  # Number of times to retry each input in case of failure.
        concurrency_limit: Optional[int] = None,  # Limit for max concurrent containers running the function.
    ) -> _Function:  # Function object - callable as a regular function within a Modal app
        """Decorator to register a new Modal function with this stub."""
        if image is None:
            image = self._get_default_image()
        mounts = [*self._get_function_mounts(raw_f), *mounts]
        function = _Function(
            raw_f,
            image=image,
            secret=secret,
            secrets=secrets,
            schedule=schedule,
            is_generator=False,
            gpu=gpu,
            rate_limit=rate_limit,
            serialized=serialized,
            mounts=mounts,
            shared_volumes=shared_volumes,
            memory=memory,
            proxy=proxy,
            retries=retries,
            concurrency_limit=concurrency_limit,
        )
        return self._add_function(function)

    @decorator_with_options
    def generator(
        self,
        raw_f=None,  # The decorated function
        *,
        image: Union[_Image, Ref] = None,  # The image to run as the container for the function
        secret: Optional[
            Union[_Secret, Ref]
        ] = None,  # An optional Modal Secret with environment variables for the container
        secrets: Collection[Union[_Secret, Ref]] = (),  # Plural version of `secret` when multiple secrets are needed
        gpu: bool = False,  # Whether a GPU is required
        rate_limit: Optional[RateLimit] = None,  # Optional RateLimit for the function
        serialized: bool = False,  # Whether to send the function over using cloudpickle.
        mounts: Collection[Union[_Mount, Ref]] = (),
        shared_volumes: Dict[str, Union[_SharedVolume, Ref]] = {},
        memory: Optional[int] = None,  # How much memory to request, in MB. This is a soft limit.
        proxy: Optional[Ref] = None,  # Reference to a Modal Proxy to use in front of this function.
        retries: Optional[int] = None,  # Number of times to retry each input in case of failure.
        concurrency_limit: Optional[int] = None,  # Limit for max concurrent containers running the function.
    ) -> _Function:
        """Decorator similar to `@modal.function`, but it wraps Python generators."""
        if image is None:
            image = self._get_default_image()
        mounts = [*self._get_function_mounts(raw_f), *mounts]
        function = _Function(
            raw_f,
            image=image,
            secret=secret,
            secrets=secrets,
            is_generator=True,
            gpu=gpu,
            rate_limit=rate_limit,
            serialized=serialized,
            mounts=mounts,
            shared_volumes=shared_volumes,
            memory=memory,
            proxy=proxy,
            retries=retries,
            concurrency_limit=concurrency_limit,
        )
        return self._add_function(function)

    @decorator_with_options
    def webhook(
        self,
        raw_f,
        *,
        method: str = "GET",  # REST method for the created endpoint.
        wait_for_response: bool = True,  # Whether requests should wait for and return the function response.
        image: Union[_Image, Ref] = None,  # The image to run as the container for the function
        secret: Optional[
            Union[_Secret, Ref]
        ] = None,  # An optional Modal Secret with environment variables for the container
        secrets: Collection[Union[_Secret, Ref]] = (),  # Plural version of `secret` when multiple secrets are needed
        gpu: bool = False,  # Whether a GPU is required
        mounts: Collection[Union[_Mount, Ref]] = (),
        shared_volumes: Dict[str, Union[_SharedVolume, Ref]] = {},
        memory: Optional[int] = None,  # How much memory to request, in MB. This is a soft limit.
        proxy: Optional[Ref] = None,  # Reference to a Modal Proxy to use in front of this function.
        retries: Optional[int] = None,  # Number of times to retry each input in case of failure.
        concurrency_limit: Optional[int] = None,  # Limit for max concurrent containers running the function.
    ):
        """Register a basic web endpoint with this application.

        This is the simplest way to create a web endpoint on Modal. The function
        behaves as a [FastAPI](https://fastapi.tiangolo.com/) handler and should
        return a response object to the caller.

        To learn how to use Modal with popular web frameworks, see the
        [guide on web endpoints](https://modal.com/docs/guide/webhooks).
        """
        if image is None:
            image = self._get_default_image()
        mounts = [*self._get_function_mounts(raw_f), *mounts]
        function = _Function(
            raw_f,
            image=image,
            secret=secret,
            secrets=secrets,
            is_generator=True,
            gpu=gpu,
            mounts=mounts,
            shared_volumes=shared_volumes,
            webhook_config=api_pb2.WebhookConfig(
                type=api_pb2.WEBHOOK_TYPE_FUNCTION, method=method, wait_for_response=wait_for_response
            ),
            memory=memory,
            proxy=proxy,
            retries=retries,
            concurrency_limit=concurrency_limit,
        )
        return self._add_function(function)

    @decorator_with_options
    def asgi(
        self,
        asgi_app,  # The asgi app
        *,
        wait_for_response: bool = True,  # Whether requests should wait for and return the function response.
        image: Union[_Image, Ref] = None,  # The image to run as the container for the function
        secret: Optional[
            Union[_Secret, Ref]
        ] = None,  # An optional Modal Secret with environment variables for the container
        secrets: Collection[Union[_Secret, Ref]] = (),  # Plural version of `secret` when multiple secrets are needed
        gpu: bool = False,  # Whether a GPU is required
        mounts: Collection[Union[_Mount, Ref]] = (),
        shared_volumes: Dict[str, Union[_SharedVolume, Ref]] = {},
        memory: Optional[int] = None,  # How much memory to request, in MB. This is a soft limit.
        proxy: Optional[Ref] = None,  # Reference to a Modal Proxy to use in front of this function.
        retries: Optional[int] = None,  # Number of times to retry each input in case of failure.
        concurrency_limit: Optional[int] = None,  # Limit for max concurrent containers running the function.
    ):
        if image is None:
            image = self._get_default_image()
        mounts = [*self._get_function_mounts(asgi_app), *mounts]
        function = _Function(
            asgi_app,
            image=image,
            secret=secret,
            secrets=secrets,
            is_generator=True,
            gpu=gpu,
            mounts=mounts,
            shared_volumes=shared_volumes,
            webhook_config=api_pb2.WebhookConfig(
                type=api_pb2.WEBHOOK_TYPE_ASGI_APP, wait_for_response=wait_for_response
            ),
            memory=memory,
            proxy=proxy,
            retries=retries,
            concurrency_limit=concurrency_limit,
        )
        return self._add_function(function)

    async def interactive_shell(self, cmd=None, mounts=[], secrets=[], image_ref=None, shared_volumes={}):
        """Run an interactive shell (like `bash`) within the image for this app.

        This is useful for online debugging and interactive exploration of the
        contents of this image. If `cmd` is optionally provided, it will be run
        instead of the default shell inside this image.

        **Example**

        ```python
        import modal

        stub = modal.Stub(image=modal.DebianSlim().apt_install(["vim"]))

        if __name__ == "__main__":
            stub.interactive_shell("/bin/bash")
        ```
        """
        from ._image_pty import image_pty

        await image_pty(image_ref or self.image, self, cmd, mounts, secrets, shared_volumes)


Stub, AioStub = synchronize_apis(_Stub)
