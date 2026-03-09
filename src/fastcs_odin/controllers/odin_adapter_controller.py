from fastcs_odin.controllers.odin_subcontroller import OdinSubController


class OdinAdapterController(OdinSubController):
    """Sub controller for an adapter in an odin control server"""

    async def initialise(self):
        await self._create_attributes()
        await self._create_commands()
