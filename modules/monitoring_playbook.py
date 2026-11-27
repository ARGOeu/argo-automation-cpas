import asyncio
import logging
import json
import ansible_runner

from argo_automation_cpas.artifacts import print_artifacts
from argo_automation_cpas.config import get_settings
from argo_automation_cpas.tokens import RestAPITokens
from argo_automation_cpas.webapi import WebAPI
from argo_automation_cpas.ams import AMS
from argo_automation_cpas.ansible_module import AnsibleModule

LOG = logging.getLogger(__name__)

KEY_SENSU_UPDATE_BACKEND: str = "sensu_update_backend"
KEY_SENSU_UPDATE_AGENT: str = "sensu_update_agent"
KEY_SENSU_ADD_TENANTS: str = "sensu_add_tenants"
KEY_SENSU_REMOVE_TENANTS: str = "sensu_remove_tenants"

class NewTenantAgentInfo:
    def __init__(self, tenant_name="", tenant_poem_host="", tenant_poem_token=""):
        self.tenant_name = tenant_name
        self.tenant_name_lower = tenant_name.lower()
        self.poem_host = tenant_poem_host
        self.poem_token = tenant_poem_token


class NewTenantBackendInfo:
    def __init__(self, tenant_name="", ams_token="", webapi_token="", poem_token=""):
        self.tenant_name = tenant_name
        self.tenant_name_lower = tenant_name.lower()
        self.ams_token = ams_token
        self.webapi_token = webapi_token
        self.poem_token = poem_token

class NewTenantEntryInfo:
    def __init__(
        self,
        tenant_agent_info: NewTenantAgentInfo,
        tenant_backend_info: NewTenantBackendInfo,
    ):
        self.tenant_agent_info = tenant_agent_info
        self.tenant_backend_info = tenant_backend_info

    def to_dict(self) -> dict:
        return {
            "tenant_name": self.tenant_agent_info.tenant_name,
            "poem_host": self.tenant_agent_info.poem_host,
            "poem_token": self.tenant_agent_info.poem_token,
            "ams_token": self.tenant_backend_info.ams_token,
            "webapi_token": self.tenant_backend_info.webapi_token
        }

class MonitoringPlaybook(AnsibleModule):
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._playbook = self.settings.ansible.sensu_playbook
        self._inventory = self.settings.ansible.sensu_inventory
        self._private_data_dir = self.settings.ansible_private_data_dir
        self.restapi_tokens = RestAPITokens()

        self._add_tenants: dict[str, NewTenantEntryInfo] = dict()
        self._remove_tenants: list[str] = []
        self._update_backend: bool = False
        self._update_agent: bool = False

    def set_add_tenants(self, in_add_tenants_list: list[str]) -> None:
        self._add_tenants = in_add_tenants_list
    
    def put_add_tenant(self, in_add_tenant: tuple[str, NewTenantEntryInfo]) -> None:
        if (in_add_tenant is not None and in_add_tenant[0] not in self._add_tenants):
            self._add_tenants.update(
                { in_add_tenant[0]: in_add_tenant[1] }
            )
    
    def set_remove_tenants(self, in_remove_tenants_list: list[str]) -> None:
        self._remove_tenants = in_remove_tenants_list
    
    def put_remove_tenant(self, in_remove_tenant: str) -> None:
        if (len(in_remove_tenant) > 0 and in_remove_tenant not in self._remove_tenants):
            self._remove_tenants.append(in_remove_tenant)

    def set_update_backend(self, in_should_update: bool) -> None:
        self._update_backend = in_should_update
    
    def set_update_agent(self, in_should_update: bool) -> None:
        self._update_agent = in_should_update

    def _setup_extravars(self) -> None:
        self.put_extravar((KEY_SENSU_UPDATE_AGENT, self._update_agent))
        self.put_extravar((KEY_SENSU_UPDATE_BACKEND, self._update_backend))

        # add tenants
        add_tenants_dict: dict = dict()
        for tenant_name, tenant_info in self._add_tenants.items():
            add_tenants_dict.update({tenant_name: tenant_info.to_dict()})
        
        self.put_extravar((KEY_SENSU_ADD_TENANTS, add_tenants_dict))
        self.put_extravar((KEY_SENSU_REMOVE_TENANTS, self._remove_tenants))

        self.put_extravar(("ansible_become", "yes"))
