""" Wrapper tasks for the SFDX CLI


TODO: Instead of everyone overriding random attrs, especially as future
users subclass these tasks, we should expose an api for the string format
function. i.e. make it easy for subclasses to add to the string inherited
from the base.

Actually do this in Command. have it expose command segments.

Then here in SFDX we will add an additional metalayer for
how the CLI formats args opts commands etc.
"""
import json

from cumulusci.core.config import ScratchOrgConfig
from cumulusci.tasks.command import Command

SFDX_CLI = "sfdx"


class SFDXBaseTask(Command):
    """ Call the sfdx cli with params and no org """

    task_options = {
        "command": {
            "description": "The full command to run with the sfdx cli.",
            "required": True,
        },
        "extra": {"description": "Append additional options to the command"},
    }

    def _get_command(self):
        command = "{SFDX_CLI} {command}".format(
            command=self.options["command"], SFDX_CLI=SFDX_CLI
        )
        return command

    def _run_task(self):
        env = self._get_env()
        command = self._get_command()
        if self.options.get("extra"):
            command += " {}".format(self.options["extra"])
        self.logger.info(f"Running command:  {command}")
        self._run_command(env, command)


class SFDXOrgTask(SFDXBaseTask):
    """ Call the sfdx cli with a workspace username """

    salesforce_task = True

    def _get_command(self):
        command = super()._get_command()
        # For scratch orgs, just pass the username in the command line
        if isinstance(self.org_config, ScratchOrgConfig):
            command += " -u {username}".format(username=self.org_config.username)
        return command

    def _get_env(self):
        env = super(SFDXOrgTask, self)._get_env()
        if not isinstance(self.org_config, ScratchOrgConfig):
            # For non-scratch keychain orgs, pass the access token via env var
            env["SFDX_INSTANCE_URL"] = self.org_config.instance_url
            env["SFDX_DEFAULTUSERNAME"] = self.org_config.access_token
        return env


class SFDXJsonTask(SFDXOrgTask):
    command = "force:mdapi:deploy --json"

    def _init_options(self, kwargs):
        super()._init_options(kwargs)
        self.options["command"] = self.command

    def _process_output(self, line):
        try:
            data = json.loads(line)
        except Exception:
            self.logger.error("Failed to parse json from line: {}".format(line))
            return

        self._process_data(data)

    def _process_data(self, data):
        self.logger.info("JSON = {}".format(data))
