from typing import Any


import asyncio
import logging
import json
import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts

LOG = logging.getLogger(__name__)

class AnsibleModule:

    def __init__(self, 
        in_playbook: str = None, 
        in_inventory: str = None, 
        in_limit: list[str] = None,
        in_extravars: dict[str, Any] = None, 
        in_envvars: dict[str, Any] = None, 
        in_private_key: str = None,
        in_private_data_dir: str = None,
    ) -> None:
        self._playbook = in_playbook
        self._inventory = in_inventory
        self._extravars = in_extravars
        self._envvars = in_envvars
        self._private_key = in_private_key
        self._private_data_dir = in_private_data_dir
        self._limit = in_limit
    
    def set_playbook(self, in_playbook: str) -> None:
        self._playbook = in_playbook
    
    def set_inventory(self, in_inventory: str) -> None:
        self._inventory = in_inventory
    
    def set_limit(self, in_limit: list[str]) -> None:
        self._limit = in_limit

    def set_extravars(self, in_extravars: dict[str, Any]) -> None:
        if self._extravars is None:
            self._extravars = dict[str, Any]()
        
        for key, val in in_extravars.items():
            self._extravars.update({key: val})
    
    def put_extravar(self, in_extravar: tuple[str, Any]) -> None:
        self.set_extravars({in_extravar[0]: in_extravar[1]})
    
    def set_envvars(self, in_envvars: dict[str, Any]) -> None:
        if self._envvars is None:
            self._envvars = dict[str, Any]()
        
        for key, val in in_envvars.items():
            self._envvars.update({key: val})
    
    def put_envvar(self, in_envvar: tuple[str, Any]) -> None:
        self.set_envvars({in_envvar[0]: in_envvar[1]})

    def set_private_key(self, in_private_key: str) -> None:
        self._private_key = in_private_key

    def set_private_data_dir(self, in_private_data_dir: str) -> None:
        self._private_data_dir = in_private_data_dir

    def _setup_extravars(self) -> Any:
        pass
    
    def _setup_envvars(self, in_strip_ansi: bool) -> None:
        if in_strip_ansi:
            self.put_envvar(("ANSIBLE_NOCOLOR", "1"))
    
    def _setup_kwargs(self, in_quiet: bool = True) -> None:
        kwargs = dict(
            private_data_dir=self._private_data_dir,
            playbook=self._playbook,
            quiet=in_quiet,
            envvars=self._envvars,
        )

        if self._extravars:
            kwargs["extravars"] = self._extravars

        if self._inventory:
            kwargs["inventory"] = self._inventory

        if self._limit:
            limit: str = ""
            for group in self._limit:
                limit += group + ","
            limit = limit[:-1]
            kwargs["host_pattern"] = limit

        if self._private_key:
            kwargs["cmdline"] = "--private-key %s" % self._private_key
        
        return kwargs

    async def run(
        self,
        quiet=True,
        strip_ansi=False,
        show_artifacts=None,
    ) -> tuple[bool, dict]:
        LOG.info(
            "Starting ansible-runner with private_data_dir=%s playbook=%s inventory=%s private_key=%s",
            self._private_data_dir,
            self._playbook,
            self._inventory or "default",
            self._private_key or "none",
        )

        self._setup_extravars()

        if not self._extravars:
            LOG.error("extravars is None!")
            return (False, dict())

        self._setup_envvars(strip_ansi)
        kwargs = self._setup_kwargs(quiet)

        runner = await asyncio.to_thread(ansible_runner.run, **kwargs)

        status = getattr(runner, "status", "unknown")
        rc = getattr(runner, "rc", "unknown")
        LOG.info("Ansible runner finished with status=%s rc=%s", status, rc)

        if show_artifacts is not None:
            print_artifacts(runner, show_artifacts)

        return (status == "successful" and rc == 0, kwargs)
