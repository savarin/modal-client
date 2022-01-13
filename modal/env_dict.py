from .object import Object
from .proto import api_pb2


class EnvDict(Object):
    """A dictionary of environment variables for images"""

    @classmethod
    async def create(cls, env_dict={}, session=None):
        session = cls.get_session(session)
        req = api_pb2.EnvDictCreateRequest(session_id=session.session_id, env_dict=env_dict)
        resp = await session.client.stub.EnvDictCreate(req)
        return cls.create_object_instance(resp.env_dict_id, session)
