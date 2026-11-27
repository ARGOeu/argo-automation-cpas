import logging

from argo_automation_cpas.config import get_settings
from argo_automation_cpas.ansible_module import AnsibleModule

LOG = logging.getLogger(__name__)

KEY_ADD_TENANTS: str = "sensu_run_check_tenants"
KEY_METRIC_PROFILE: str = "sensu_run_check_metricprofile"

class RunCheckPlaybook(AnsibleModule):
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._playbook = self.settings.ansible.sensu_run_check_playbook
        self._inventory = self.settings.ansible.sensu_inventory
        self.set_limit(["sensu-backend"])

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
