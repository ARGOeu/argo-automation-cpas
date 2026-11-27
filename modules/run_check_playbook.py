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

KEY_ADD_TENANTS: str = "sensu_run_check_tenants"
KEY_METRIC_PROFILE: str = "sensu_run_check_metricprofile"

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

class RunCheckPlaybook(AnsibleModule):
    def __init__(self):
        super().__init__()
        self._playbook = "sensu-run-check.yml"
        self._inventory = "sensu-next.yml"
        self.set_limit(["sensu-backend"])
        self.settings = get_settings()
        self.restapi_tokens = RestAPITokens()

        self._update_tenants: list[str] = []
        self._metric_profile: str | None = None

    def add_tenants(self, in_add_tenants_list: list[str]) -> None:
        self._update_tenants = in_add_tenants_list
    
    def add_tenant(self, in_add_tenant: tuple[str, NewTenantEntryInfo]) -> None:
        if (in_add_tenant is not None and in_add_tenant[0] not in self._update_tenants):
            self._update_tenants.update(
                { in_add_tenant[0]: in_add_tenant[1] }
            )

    def set_metric_profile(self, in_metric_profile: str) -> None:
        self._metric_profile = in_metric_profile

    def _setup_extravars(self) -> None:
        if len(self._update_tenants) > 0:
            self.put_extravar((KEY_ADD_TENANTS, self._update_tenants))

        if self._metric_profile != "None":
            self.put_extravar((KEY_METRIC_PROFILE, self._metric_profile))

        self.put_extravar(("ansible_become", "yes"))
