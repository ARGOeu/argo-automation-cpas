import asyncio
import datetime
import logging
import os
import subprocess
import uuid
import yaml
import tempfile
import shutil
from git import Repo
from enum import Enum

from argo_automation_cpas.monitoring_playbook import (
    MonitoringPlaybook, 
    NewTenantAgentInfo, 
    NewTenantBackendInfo, 
    NewTenantEntryInfo
)

class MonboxAddTenantResult(Enum):
    SUCCESS = 0,
    ALREADY_ADDED = 1,
    ERROR = 2

import ansible_runner

from argo_automation_cpas.config import get_settings

LOG = logging.getLogger(__name__)

class TenantActionInfo:
    def __init__(self, tenant_name, action="NONE"):
        self.tenant_name = tenant_name
        self.action = action


class MonboxGit:
    def __init__(self):
        self.settings = get_settings()
        self.new_tenant_entries: list[NewTenantEntryInfo] = []
        self.remove_tenant_entries: list[str] = []
        self.updated_tenants: list[TenantActionInfo] = []

    def add_new_tenant(self, webapi, ams, new_tenant_name, rest_api_tokens) -> MonboxAddTenantResult:
        tenant_name_lower = new_tenant_name.lower()

        if self._is_tenant_already_added(new_tenant_name):
            LOG.info(f"Tenant {new_tenant_name} already queued to be added!")
            return MonboxAddTenantResult.ALREADY_ADDED

        restApiToken = rest_api_tokens.get(new_tenant_name)

        if restApiToken is None:
            LOG.error(
                "There is no restapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return MonboxAddTenantResult.ERROR

        restApiToken = restApiToken.get("restapi")

        monbox_webapi_component = "monbox"
        webapi_tokens = webapi.tokens.load_tokens(self.settings.webapi.tokens_spool)
        webapi_tokens = webapi_tokens.get(new_tenant_name)

        if webapi_tokens is None:
            LOG.error(
                "There is no webapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return MonboxAddTenantResult.ERROR

        webapi_token = webapi_tokens.get(monbox_webapi_component)

        if webapi_token is None:
            LOG.error(
                "There is no monbox webapi_token for tenant with id: "
                + new_tenant_name
                + "; Exiting early."
            )
            return MonboxAddTenantResult.ERROR

        monbox_ams_component = "argo-monbox"
        ams_tokens = ams.tokens.load_tokens(self.settings.ams.tokens_spool)
        ams_tokens = ams_tokens.get(new_tenant_name)

        if ams_tokens is None:
            LOG.error(
                "There is no ams_token for tenant with id: " + new_tenant_name + "; Exiting early."
            )
            return MonboxAddTenantResult.ERROR

        ams_token = ams_tokens.get(monbox_ams_component)
        if ams_token is None:
            LOG.error(
                f"There is no argo-monbox ams_token for tenant with id: {new_tenant_name}; Exiting early."
            )
            return MonboxAddTenantResult.ERROR

        new_tenant_agent_info = NewTenantAgentInfo(
            tenant_name=new_tenant_name,
            tenant_poem_host=tenant_name_lower + ".poem.devel.mon.argo.grnet.gr",
            tenant_poem_token=restApiToken,
        )

        new_tenant_backend_info = NewTenantBackendInfo(
            tenant_name=new_tenant_name,
            ams_token=ams_token,
            webapi_token=webapi_token,
            poem_token=restApiToken,
        )

        self._add_tenant_to_array(
            NewTenantEntryInfo(new_tenant_agent_info, new_tenant_backend_info)
        )

        return MonboxAddTenantResult.SUCCESS
    
    def add_remove_tenant(self, tenant_name) -> None:
        if (tenant_name not in self.remove_tenant_entries):
            self.remove_tenant_entries.append(tenant_name)

    async def commit_tenants(self):
        backend_commit_status = await self._commit_sensu_backend_changes()
        agent_commit_status = await self._commit_sensu_agent_changes()

        success = backend_commit_status and agent_commit_status
        return success

    async def start_monbox_init_check(self):
        LOG.info(f"MonboxGit | Starting monbox init check on backend machine(s).")

        whoami_cmd = "whoami"
        shell_script_cmd = "ams-publisherd -q"

        kwargs = dict(
            private_data_dir=self.settings.ansible_private_data_dir,
            inventory=f"inventory/{self.settings.ansible.sensu_inventory}",
            host_pattern="sensu-backend",
            module="shell",
            quiet=True,
            module_args=shell_script_cmd,
        )

        kwargs["inventory"] = self.settings.ansible.sensu_inventory

        private_key = self.settings.ansible.ssh_private_key
        if private_key:
            kwargs["cmdline"] = "--private-key %s" % private_key

        extravars = {}
        extravars["ansible_become"] = "yes"

        kwargs["extravars"] = extravars

        r = await asyncio.to_thread(ansible_runner.run, **kwargs)

        LOG.info(f"Runner finished (rc={r.rc})")

        all_tenants_inited, inited_tenants = self._check_if_all_tenants_inited(r.events)

        return all_tenants_inited, inited_tenants

    def clear_added_tenants(self):
        self.new_tenant_entries.clear()

    def _is_tenant_already_added(self, new_tenant_name):
        for tenant in self.new_tenant_entries:
            if tenant.tenant_agent_info.tenant_name.lower() == new_tenant_name.lower():
                return True

        return False

    def _add_tenant_to_array(self, new_tenant_entry: NewTenantEntryInfo):
        self.new_tenant_entries.append(new_tenant_entry)
        self.updated_tenants.append(
            TenantActionInfo(new_tenant_entry.tenant_agent_info.tenant_name, "Added")
        )

    async def _commit_sensu_backend_changes(self):
        playbook_instance = MonitoringPlaybook()
        playbook_instance.set_update_backend(True)
        playbook_instance.set_limit(['sensu-backend'])

        for tenant in self.new_tenant_entries:
            playbook_instance.put_add_tenant(
                (tenant.tenant_backend_info.tenant_name, 
                tenant)
            )
        
        for tenant_name in self.remove_tenant_entries:
            playbook_instance.put_remove_tenant(tenant_name)

        LOG.info("Starting playbook for sensu backend changes.")

        (success, kwargs) = await playbook_instance.run(quiet=False)

        return success

    async def _commit_sensu_agent_changes(self):
        playbook_instance = MonitoringPlaybook()
        playbook_instance.set_update_agent(True)
        playbook_instance.set_limit(['sensu-agent'])
        
        for tenant in self.new_tenant_entries:
            playbook_instance.put_add_tenant(
                (tenant.tenant_agent_info.tenant_name, 
                tenant)
            )
        
        for tenant_name in self.remove_tenant_entries:
            playbook_instance.put_remove_tenant(tenant_name)
        
        LOG.info("Starting playbook for sensu agent changes.")
        
        (success, kwargs) = await playbook_instance.run(quiet=False)

        return success

    def _check_if_all_tenants_inited(self, events):
        line_prefix = "INFO - worker:metrics"
        line_prefix_len = len(line_prefix)
        inited_tenants = []

        for event in events:
            if event.get("event", "") == "runner_on_ok":
                # this is the output of the run command
                result = event["event_data"]["res"]["stdout"]
                lines = result.split("\n")
                end_command = ""
                for line in lines:
                    # pass through tenants only once (published/consumed)
                    if len(end_command) != 0 and line.find(end_command) != -1:
                        break

                    # if first msg is published, then only go through published msgs
                    if len(end_command) == 0:
                        if line.find("published"):
                            end_command = "consumed"
                        elif line.find("consumed"):
                            end_command = "published"

                    # get name of tenant
                    first_reverse_whitespace = line.rfind(" ")
                    tenant_name = line[line_prefix_len:first_reverse_whitespace]
                    tenant_name_lower = tenant_name.lower()

                    # check if the current tenant is one of the ones added in this pass
                    found_tenant = self._is_tenant_already_added(tenant_name)
                    if not found_tenant:
                        continue

                    # confirm tenant init
                    LOG.info(f"Tenant {tenant_name_lower} monbox init confirmed.")
                    inited_tenants.append(tenant_name_lower)

        all_tenants_inited = len(inited_tenants) == len(self.new_tenant_entries)

        # print warning for tenants that weren't confirmed inited
        if not all_tenants_inited:
            not_inited_tenants_str = ""
            for new_tenant in self.new_tenant_entries:
                new_tenant_name_lower = new_tenant.tenant_agent_info.tenant_name_lower
                if new_tenant_name_lower not in inited_tenants:
                    not_inited_tenants_str += f"{new_tenant_name_lower} "
            LOG.warning(f"Unable to confirm monbox init for tenants: {not_inited_tenants_str}")

        return all_tenants_inited, inited_tenants

