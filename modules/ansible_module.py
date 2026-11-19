from typing import Any


import asyncio
import logging
import json
import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts

LOG = logging.getLogger(__name__)

class AnsibleModule:
    self.__playbook: str = None
    self.__inventory: str = None
    self.__limit: list[str] = None
    self.__extravars: dict[str, dict] = None
    self.__envvars: dict = None
    self.__private_key: str = None
    self.__private_data_dir: str = None

    def __init__(self) -> None:
        pass

    def __init__(self, 
        in_playbook: str, 
        in_inventory: str, 
        in_limit: list[str],
        in_extravars: dict[str, Any], 
        in_envvars: dict[str, Any], 
        in_private_key: str,
        in_private_data_dir: str,
    ) -> None:
        self.__playbook = in_playbook
        self.__inventory = in_inventory
        self.__extravars = in_extravars
        self.__envvars = in_envvars
        self.__private_key = in_private_key
        self.__private_data_dir = in_private_data_dir
        self.__limit = in_limit
    
    def set_playbook(self, in_playbook: str) -> None:
        self.__playbook = in_playbook
    
    def set_inventory(self, in_inventory: str) -> None:
        self.__inventory = in_inventory
    
    def set_limit(self, in_limit: list[str]) -> None:
        self.__limit = in_limit

    def set_extravars(self, in_extravars: dict[str, Any]) -> None:
        if self.__extravars is None:
            self.__extravars = dict[str, Any]()
        
        for key, val in in_extravars.items():
            self.__extravars.update(key, val)
    
    def put_extravar(self, in_extravar: tuple[str, Any]) -> None:
        self.set_extravars([in_extravar])
    
    def set_envvars(self, in_envvars: dict[str, Any]) -> None:
        if self.__envvars is None:
            self.__envvars = dict[str, Any]()
        
        for key, val in in_envvars.items():
            self.__envvars.update(key, val)
    
    def put_envvar(self, in_envvar: tuple[str, Any]) -> None:
        self.set_envvars([in_envvar])

    def set_private_key(self, in_private_key: str) -> None:
        self.__private_key = in_private_key

    def set_private_data_dir(self, in_private_data_dir: str) -> None:
        self.__private_data_dir = in_private_data_dir

    def _setup_extravars(self) -> Any:
        pass
    
    def _setup_envvars(self, in_strip_ansi: bool) -> None:
        if self.__strip_ansi:
            self.put_envvar(("ANSIBLE_NOCOLOR", "1"))
    
    def _setup_kwargs(self) -> None:
        kwargs = dict(
            private_data_dir=self.__private_data_dir,
            playbook=self.__playbook,
            quiet=True,
            envvars=self.__envvars,
        )

        if self.__extravars:
            kwargs["extravars"] = self.__extravars

        if self.__inventory:
            kwargs["inventory"] = self.__inventory

        if self.__limit:
            limit: str = ""
            for group in self.__limit:
                limit += group + ","
            limit = limit[:-1]
            kwargs["host_pattern"] = limit

        if private_key:
            kwargs["cmdline"] = "--private-key %s" % self.__private_key
        
        return kwargs

    async def run(
        self,
        strip_ansi=False,
        show_artifacts=None,
    ) -> tuple[bool, dict]:
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self.__private_data_dir,
            self.__playbook,
            self.__inventory or "default",
            self.__private_key or "none",
        )

        self._setup_extravars()

        if not self.__extravars:
            LOG.error("extravars is None!")
            return (False, dict())

        self._setup_envvars(strip_ansi)
        kwargs = self._setup_kwargs()

        runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

        if show_artifacts is not None:
            print_artifacts(runner, show_artifacts)

        return (status == "successful" and rc == 0, kwargs)
