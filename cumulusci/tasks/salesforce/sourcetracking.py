from collections import defaultdict
import os
import re
import xmltodict

from cumulusci.core.utils import process_list_arg
from cumulusci.salesforce_api.metadata import ApiRetrieveUnpackaged
from cumulusci.tasks.salesforce import BaseRetrieveMetadata
from cumulusci.tasks.salesforce import BaseSalesforceApiTask
from cumulusci.tasks.metadata.package import PackageXmlGenerator
from cumulusci.tasks.metadata.package import __location__


class ListChanges(BaseSalesforceApiTask):

    task_options = {
        "include": {"description": "Include changed components matching this string."},
        "exclude": {"description": "Exclude changed components matching this string."},
        "exclude_namespace": {"description": "Namespaces that should be excluded."},
    }

    def _init_options(self, kwargs):
        super(ListChanges, self)._init_options(kwargs)
        self.options["include"] = process_list_arg(self.options.get("include", []))
        self.options["exclude"] = process_list_arg(self.options.get("exclude", []))
        self.options["exclude_namespace"] = process_list_arg(
            self.options.get("exclude_namespace", [])
        )
        self._exclude = self.options.get("exclude", [])
        for namespace in self.options["exclude_namespace"]:
            self._exclude.append("CustomField: .*\.{}__.*__c".format(namespace))
            self._exclude.append("CompactLayout: .*\.{}__.*__c".format(namespace))
        if self.project_config.project__source__ignore:
            self._exclude.extend(self.project_config.project__source__ignore)

    def _get_changes(self):
        changes = self.tooling.query(
            "SELECT MemberName, MemberType FROM SourceMember WHERE IsNameObsolete=false"
        )
        return changes

    def _run_task(self):
        changes = self._get_changes()
        if changes["totalSize"]:
            self.logger.info(
                "Found {} changed components in the scratch org:".format(
                    changes["totalSize"]
                )
            )

        filtered = self._filter_changes(changes)
        for change in filtered:
            self.logger.info("{MemberType}: {MemberName}".format(**change))
        if not filtered:
            self.logger.info("Found no changes.")

        ignored = len(changes["records"]) - len(filtered)
        if ignored:
            self.logger.info(
                "Ignored {} changed components in the scratch org:".format(ignored)
            )

    def _filter_changes(self, changes):
        filtered = []
        for change in changes["records"]:
            mdtype = change["MemberType"]
            name = change["MemberName"]
            full_name = "{}: {}".format(mdtype, name)
            if self.options["include"] and not any(
                re.search(s, full_name) for s in self.options["include"]
            ):
                continue
            if any(re.search(s, full_name) for s in self._exclude):
                continue
            filtered.append(change)
        return filtered


retrieve_changes_task_options = ListChanges.task_options.copy()
retrieve_changes_task_options["path"] = {
    "description": "The path to write the retrieved metadata",
    "required": True,
}
retrieve_changes_task_options["api_version"] = {
    "description": (
        "Override the default api version for the retrieve."
        + " Defaults to project__package__api_version"
    )
}


class RetrieveChanges(BaseRetrieveMetadata, ListChanges, BaseSalesforceApiTask):
    api_class = ApiRetrieveUnpackaged

    task_options = retrieve_changes_task_options

    def _init_options(self, kwargs):
        super(RetrieveChanges, self)._init_options(kwargs)

        if "api_version" not in self.options:
            self.options[
                "api_version"
            ] = self.project_config.project__package__api_version

    def _get_api(self):
        self.logger.info("Querying Salesforce for changed source members")
        changes = self.tooling.query(
            "SELECT MemberName, MemberType FROM SourceMember WHERE IsNameObsolete=false"
        )

        type_members = defaultdict(list)
        filtered = self._filter_changes(changes)
        if not filtered:
            self.logger.info("No changes to retrieve")
            return
        for change in filtered:
            type_members[change["MemberType"]].append(change["MemberName"])
            self.logger.info("{MemberType}: {MemberName}".format(**change))

        package_xml_path = os.path.join(self.options["path"], "package.xml")
        if os.path.isfile(package_xml_path):
            with open(package_xml_path, "rb") as f:
                current_package_xml = xmltodict.parse(f)
        else:
            current_package_xml = {"Package": {}}
        merged_type_members = {}
        for mdtype in current_package_xml["Package"].get("types", []):
            if "members" not in mdtype:
                continue
            members = []
            if isinstance(mdtype["members"], str):
                members.append(mdtype["members"])
            else:
                for item in mdtype["members"]:
                    members.append(item)
            if members:
                merged_type_members[mdtype["name"]] = members

        types = []
        for name, members in type_members.items():
            if name in merged_type_members:
                merged_type_members[name].extend(members)
            else:
                merged_type_members[name] = members

        for name, members in type_members.items():
            types.append(MetadataType(name, members))
        package_xml = PackageXmlGenerator(self.options["api_version"], types=types)()

        return self.api_class(self, package_xml, self.options.get("api_version"))

    def _run_task(self):
        changes = self._get_changes()
        super(RetrieveChanges, self)._run_task()

        # update package.xml
        package_xml = PackageXmlGenerator(
            directory=self.options["path"],
            api_version=self.options["api_version"],
            package_name=self.project_config.project__package__name,
        )()
        with open(os.path.join(self.options["path"], "package.xml"), "w") as f:
            f.write(package_xml)


class MetadataType(object):
    def __init__(self, name, members):
        self.metadata_type = name
        self.members = members

    def __call__(self):
        members = ["<members>{}</members>".format(member) for member in self.members]
        return """<types>
    {}
    <name>{}</name>
</types>""".format(
            members, self.metadata_type
        )
