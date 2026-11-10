"""
Dependency Validation System for Production AI Model Deployments
Analyzes container configurations and dependency files to detect potential conflicts before deployment.
"""

import os
import re
import sys
import json
import argparse
from typing import Dict, List, Tuple, Optional, Any
from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.version import Version, InvalidVersion
from packaging.utils import canonicalize_name


class DependencyValidator:
    """
    Validates Dockerfiles and requirements files to ensure dependency compatibility,
    detect version conflicts, and generate deployment readiness reports.
    """

    KNOWN_ECOSYSTEM_INCOMPATIBILITIES = [
        {
            "package_a": "numpy",
            "spec_a": ">=2.0.0",
            "package_b": "scikit-learn",
            "spec_b": "<1.3.0",
            "reason": "NumPy 2.0+ introduces breaking C-API changes incompatible with scikit-learn < 1.3.0."
        },
        {
            "package_a": "numpy",
            "spec_a": ">=2.0.0",
            "package_b": "scipy",
            "spec_b": "<1.12.0",
            "reason": "NumPy 2.0+ requires SciPy >= 1.12.0 for ABI compatibility."
        },
        {
            "package_a": "flask",
            "spec_a": "<2.0.0",
            "package_b": "werkzeug",
            "spec_b": ">=3.0.0",
            "reason": "Flask < 2.0.0 is incompatible with modern Werkzeug 3.x WSGI internals."
        }
    ]

    def __init__(self):
        self.dependencies: Dict[str, List[Dict[str, Any]]] = {}
        self.conflicts: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.scanned_files: List[str] = []

    def parse_requirements_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parses a requirements.txt file and extracts package dependencies."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Requirements file not found: {file_path}")

        extracted = []
        self.scanned_files.append(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Strip inline comments
                if " #" in line:
                    line = line.split(" #", 1)[0].strip()

                # Ignore flag lines like -r, -f, -i
                if line.startswith("-"):
                    continue

                try:
                    req = Requirement(line)
                    pkg_name = canonicalize_name(req.name)
                    dep_info = {
                        "name": pkg_name,
                        "raw": line,
                        "specifier": str(req.specifier) if req.specifier else "",
                        "specifier_set": req.specifier,
                        "extras": list(req.extras),
                        "marker": str(req.marker) if req.marker else None,
                        "source_file": file_path,
                        "line_number": line_no
                    }
                    extracted.append(dep_info)
                    self._record_dependency(dep_info)
                except InvalidRequirement as e:
                    self.warnings.append({
                        "file": file_path,
                        "line": line_no,
                        "raw": line,
                        "warning": f"Could not parse requirement syntax: {e}"
                    })

        return extracted

    def parse_dockerfile(self, file_path: str) -> List[Dict[str, Any]]:
        """Parses a Dockerfile to extract dependencies installed via RUN commands or requirements copies."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dockerfile not found: {file_path}")

        extracted = []
        self.scanned_files.append(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            # Match pip install commands
            if line.startswith("RUN") and "pip install" in line:
                # Find all quoted or unquoted package arguments
                # Avoid flags like -r, --no-cache-dir, --upgrade
                tokens = line.replace("&&", "\n").split()
                for token in tokens:
                    token = token.strip('\'",;\\')
                    if (
                        token.startswith("-") or
                        "pip" in token or
                        "install" in token or
                        "RUN" in token or
                        token.endswith(".txt") or
                        token in ["update", "apt-get", "curl", "python"]
                    ):
                        continue

                    try:
                        req = Requirement(token)
                        pkg_name = canonicalize_name(req.name)
                        dep_info = {
                            "name": pkg_name,
                            "raw": token,
                            "specifier": str(req.specifier) if req.specifier else "",
                            "specifier_set": req.specifier,
                            "extras": list(req.extras),
                            "marker": str(req.marker) if req.marker else None,
                            "source_file": file_path,
                            "line_number": line_no
                        }
                        extracted.append(dep_info)
                        self._record_dependency(dep_info)
                    except InvalidRequirement:
                        pass

        return extracted

    def _record_dependency(self, dep_info: Dict[str, Any]):
        """Internal registry for tracking all extracted dependencies."""
        name = dep_info["name"]
        if name not in self.dependencies:
            self.dependencies[name] = []
        self.dependencies[name].append(dep_info)

    def are_specifiers_compatible(self, spec_a: SpecifierSet, spec_b: SpecifierSet) -> Tuple[bool, str]:
        """
        Tests whether two packaging SpecifierSets can be simultaneously satisfied.
        Uses boundary analysis and candidate test releases.
        """
        # If either has no constraints, they are trivially compatible
        if not spec_a or not spec_b:
            return True, "Compatible (unbounded specifier)"

        # Check explicit equality pins
        exact_a = [s.version for s in spec_a if s.operator in ("==", "===")]
        exact_b = [s.version for s in spec_b if s.operator in ("==", "===")]

        if exact_a and exact_b:
            if exact_a[0] != exact_b[0]:
                return False, f"Conflicting pinned versions: {exact_a[0]} != {exact_b[0]}"

        if exact_a:
            v = Version(exact_a[0])
            if v not in spec_b:
                return False, f"Pinned version {v} does not satisfy specifier {spec_b}"
            return True, f"Pinned version {v} satisfies both"

        if exact_b:
            v = Version(exact_b[0])
            if v not in spec_a:
                return False, f"Pinned version {v} does not satisfy specifier {spec_a}"
            return True, f"Pinned version {v} satisfies both"

        # Check upper and lower bounds for intersection overlap
        # Collect candidate probe versions based on boundary limits
        test_candidates = set()
        for spec in (list(spec_a) + list(spec_b)):
            try:
                base_v = Version(spec.version)
                test_candidates.add(str(base_v))
                # Add micro-variations around the boundary
                parts = str(base_v).split(".")
                if len(parts) >= 2 and parts[-1].isdigit():
                    last_num = int(parts[-1])
                    if last_num > 0:
                        test_candidates.add(".".join(parts[:-1] + [str(last_num - 1)]))
                    test_candidates.add(".".join(parts[:-1] + [str(last_num + 1)]))
                test_candidates.add(f"{parts[0]}.0.0")
                test_candidates.add(f"{int(parts[0]) + 1}.0.0")
            except InvalidVersion:
                continue

        # Check if any candidate version satisfies both specifier sets
        found_overlap = False
        for cand in sorted(test_candidates):
            try:
                v = Version(cand)
                if (v in spec_a) and (v in spec_b):
                    found_overlap = True
                    break
            except InvalidVersion:
                continue

        if not found_overlap and len(test_candidates) > 0:
            # Let's check direct bounds: e.g. <2.0.0 and >=2.0.0
            return False, f"Specifier sets {spec_a} and {spec_b} have disjoint version domains."

        return True, "Overlapping version domain found"

    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """Identifies version incompatibilities across all recorded dependencies and ecosystem rules."""
        self.conflicts = []

        # 1. Intra-package version conflicts across files or declarations
        for pkg_name, occurrences in self.dependencies.items():
            if len(occurrences) < 2:
                continue

            for i in range(len(occurrences)):
                for j in range(i + 1, len(occurrences)):
                    dep1 = occurrences[i]
                    dep2 = occurrences[j]

                    spec1 = dep1["specifier_set"]
                    spec2 = dep2["specifier_set"]

                    if spec1 and spec2:
                        compatible, reason = self.are_specifiers_compatible(spec1, spec2)
                        if not compatible:
                            self.conflicts.append({
                                "type": "VERSION_COLLISION",
                                "package": pkg_name,
                                "source_a": f"{dep1['source_file']}:{dep1['line_number']} ({dep1['raw']})",
                                "source_b": f"{dep2['source_file']}:{dep2['line_number']} ({dep2['raw']})",
                                "specifier_a": str(spec1),
                                "specifier_b": str(spec2),
                                "reason": reason,
                                "remediation": f"Align '{pkg_name}' version bounds in both files to a shared compatible release."
                            })

        # 2. Cross-package ecosystem incompatibilities
        for rule in self.KNOWN_ECOSYSTEM_INCOMPATIBILITIES:
            pkg_a = canonicalize_name(rule["package_a"])
            pkg_b = canonicalize_name(rule["package_b"])

            if pkg_a in self.dependencies and pkg_b in self.dependencies:
                deps_a = self.dependencies[pkg_a]
                deps_b = self.dependencies[pkg_b]

                rule_spec_a = SpecifierSet(rule["spec_a"])
                rule_spec_b = SpecifierSet(rule["spec_b"])

                for da in deps_a:
                    for db in deps_b:
                        # Check if da and db trigger rule conditions
                        spec_a = da["specifier_set"]
                        spec_b = db["specifier_set"]

                        # If da could overlap with rule_spec_a AND db could overlap with rule_spec_b
                        compat_a, _ = self.are_specifiers_compatible(spec_a, rule_spec_a)
                        compat_b, _ = self.are_specifiers_compatible(spec_b, rule_spec_b)

                        if compat_a and compat_b:
                            self.conflicts.append({
                                "type": "ECOSYSTEM_INCOMPATIBILITY",
                                "package": f"{pkg_a} + {pkg_b}",
                                "source_a": f"{da['source_file']} ({da['raw']})",
                                "source_b": f"{db['source_file']} ({db['raw']})",
                                "specifier_a": str(spec_a),
                                "specifier_b": str(spec_b),
                                "reason": rule["reason"],
                                "remediation": f"Upgrade or constrain {pkg_b} to be compatible with {pkg_a} {rule['spec_a']}."
                            })

        return self.conflicts

    def generate_report(self) -> Dict[str, Any]:
        """Generates a structured deployment readiness validation report."""
        has_conflicts = len(self.conflicts) > 0
        has_warnings = len(self.warnings) > 0

        if has_conflicts:
            status = "DEPLOYMENT_BLOCKED"
            message = f"Found {len(self.conflicts)} dependency conflict(s). Deployment cannot proceed."
        elif has_warnings:
            status = "NEEDS_ATTENTION"
            message = "Dependencies parsed with minor syntax or deprecation warnings. Deployment may proceed with caution."
        else:
            status = "READY_FOR_DEPLOYMENT"
            message = "All dependencies validated successfully. Zero conflicts detected."

        report = {
            "validation_status": status,
            "ready_for_deployment": not has_conflicts,
            "message": message,
            "summary": {
                "scanned_files": self.scanned_files,
                "total_packages_tracked": len(self.dependencies),
                "total_conflicts": len(self.conflicts),
                "total_warnings": len(self.warnings)
            },
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "dependencies_catalog": {
                pkg: [
                    {
                        "source": dep["source_file"],
                        "raw": dep["raw"],
                        "specifier": dep["specifier"]
                    }
                    for dep in occurrences
                ]
                for pkg, occurrences in self.dependencies.items()
            }
        }
        return report

    def export_markdown_report(self, report: Dict[str, Any], output_path: str):
        """Exports the validation report as a clean GitHub Flavored Markdown document."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        status = report["validation_status"]
        status_badge = (
            "🟢 **READY FOR DEPLOYMENT**" if status == "READY_FOR_DEPLOYMENT"
            else "🟡 **NEEDS ATTENTION**" if status == "NEEDS_ATTENTION"
            else "🔴 **DEPLOYMENT BLOCKED**"
        )

        md = []
        md.append("# 📦 AI Deployment Dependency Validation Report\n")
        md.append(f"**Readiness Status:** {status_badge}\n")
        md.append(f"**Verdict:** {report['message']}\n")
        md.append("## 📊 Summary\n")
        md.append(f"- **Scanned Files:** `{', '.join(report['summary']['scanned_files'])}`")
        md.append(f"- **Total Packages Tracked:** {report['summary']['total_packages_tracked']}")
        md.append(f"- **Conflicts Detected:** {report['summary']['total_conflicts']}")
        md.append(f"- **Warnings Detected:** {report['summary']['total_warnings']}\n")

        if report["conflicts"]:
            md.append("## ❌ Detected Incompatibilities\n")
            md.append("| Type | Package | Source A | Source B | Root Cause | Remediation |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for c in report["conflicts"]:
                md.append(
                    f"| `{c['type']}` | **{c['package']}** | `{c['source_a']}` | `{c['source_b']}` | {c['reason']} | {c['remediation']} |"
                )
            md.append("")
        else:
            md.append("## ✅ Verification Passed\n")
            md.append("No version collisions or known package incompatibilities detected across container configurations.\n")

        if report["warnings"]:
            md.append("## ⚠️ Warnings\n")
            for w in report["warnings"]:
                md.append(f"- **{w.get('file', 'General')}**: {w.get('warning', '')} (`{w.get('raw', '')}`)")
            md.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))


def validate_deployment_files(
    requirements_files: List[str],
    dockerfiles: Optional[List[str]] = None,
    output_json: Optional[str] = None,
    output_md: Optional[str] = None
) -> Dict[str, Any]:
    """Helper entry point to execute validation across multiple files."""
    validator = DependencyValidator()

    for rf in requirements_files:
        if os.path.exists(rf):
            validator.parse_requirements_file(rf)

    if dockerfiles:
        for df in dockerfiles:
            if os.path.exists(df):
                validator.parse_dockerfile(df)

    validator.detect_conflicts()
    report = validator.generate_report()

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    if output_md:
        validator.export_markdown_report(report, output_md)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Deployment Dependency Validation Tool")
    parser.add_argument("--reqs", nargs="+", default=["requirements.txt"], help="Paths to requirements.txt files")
    parser.add_argument("--dockerfile", nargs="*", default=["Dockerfile"], help="Paths to Dockerfile files")
    parser.add_argument("--json", default="reports/validation_report.json", help="Path to output JSON report")
    parser.add_argument("--md", default="reports/validation_report.md", help="Path to output Markdown report")

    args = parser.parse_args()
    report = validate_deployment_files(args.reqs, args.dockerfile, args.json, args.md)

    print("\n" + "=" * 60)
    print(f"DEPLOYMENT VALIDATION: {report['validation_status']}")
    print(f"{report['message']}")
    print("=" * 60)
    if report["conflicts"]:
        print(f"\n[!] Found {len(report['conflicts'])} conflict(s):")
        for idx, conf in enumerate(report["conflicts"], 1):
            print(f"  {idx}. [{conf['type']}] {conf['package']}")
            print(f"     A: {conf['source_a']}")
            print(f"     B: {conf['source_b']}")
            print(f"     Reason: {conf['reason']}")
            print(f"     Fix: {conf['remediation']}\n")
        sys.exit(1)
    else:
        print("[✓] All dependency constraints validated cleanly. Ready for deployment.\n")
        sys.exit(0)

