# Public repository readiness

Reviewed on **2026-10-26** for the intended use: a user-installed desktop utility
that visually blanks selected displays in the user's own Hyprland session.

## GitHub policy assessment

The review found no conflict between that intended behavior and GitHub's
relevant hosting policies. This is a scoped review of this source package;
GitHub retains discretion over hosting and enforcement.

- **Acceptable use, authenticity and privacy:** the code is readable and the
  README describes its input interception, cursor setting, process lifecycle
  and recovery. No account impersonation, unauthorized access functionality,
  telemetry, embedded credentials, personal desktop screenshots or private
  machine configuration is included. See GitHub's
  [Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies).
- **Malware policy:** the intended operation is explicit local-user display
  control with a recovery route. The source includes no attack infrastructure,
  covert persistence or remote command-and-control service. This review found
  none of the prohibited attack-support activity described in the
  [active malware or exploits policy](https://docs.github.com/en/site-policy/acceptable-use-policies/github-active-malware-or-exploits).
- **Rights and licensing:** original project files have an MIT licence. The
  separate layer-shell protocol notice is retained verbatim, and its checksum
  is recorded. Generated binaries and protocol bindings are omitted from the
  source package. GitHub recommends including a licence for open-source reuse;
  it does not require every public repository to use an open-source licence.
  See [licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
- **AI tools:** this project does not generate synthetic media or promote the
  prohibited uses in GitHub's
  [synthetic media and AI tools policy](https://docs.github.com/en/site-policy/acceptable-use-policies/github-synthetic-media-and-ai-tools).
  AI-assisted development is described in the contribution guidance without
  asserting that GitHub has reviewed or endorsed the code.

## Prepared safeguards

The release and installer use explicit file allowlists. Release metadata is
normalized, with reproducible source archives and SHA-256 checksums. The
publication check validates licence/notice presence, the protocol checksum,
manifest/catalog agreement, file sizes, unexpected binaries/symlinks, known
credential patterns and personal absolute home paths. Pattern scanning is
supplementary; contributors must still review everything they publish.

The only preview is original, self-contained vector artwork labelled as an
illustration. It includes no captured desktop content or external assets.
The Git repository begins with this reviewed source set, without importing
local session history, runtime state or installed build output.

GitHub Actions uses normal push/PR events, read-only repository contents,
full-commit pins for GitHub-owned actions, no persisted checkout credentials,
no repository secrets, concurrency cancellation and job time limits. The
workflow does not use privileged pull-request-target execution or interpolate
issue/PR text into shell scripts. Dependabot is configured for action updates.
These follow GitHub's [secure use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

## Local checks and remaining hosting settings

Run from the repository root:

```sh
python3 -B scripts/check_project.py
python3 -B -m unittest discover -s screen-blackout/tests -v
python3 -B -m unittest discover -s tests -v
CFLAGS="-Werror -fanalyzer" screen-blackout/build-helper.sh
python3 -B scripts/release.py
git diff --cached --check
```

The tests use temporary data/runtime directories, simulated compositor replies,
and local compilation. They do not alter the working desktop installation.
The CI workflow is prepared; actual GitHub-hosted execution can be checked only
after the repository is pushed.

For the prepared 1.4.12 source set, all **20 runtime regression checks and nine
packaging checks passed locally**. Packaging checks include build/install,
guarded replacement and backup, uninstall, build-failure preservation,
reproducible archives, and installation from an extracted source release.
The native helper compiled with warnings treated as errors and GCC's analyzer.
ShellCheck 0.11.0 passed; the local tool's official release checksum was verified.
Workflow/issue-template YAML parsed successfully. The 32-file public allowlist,
credential-pattern scan, attribution checks and staged whitespace check passed.
This source review found no embedded credentials or private machine data.

After creating a repository, recommended hosting settings include secret
scanning/push protection where available, private vulnerability reporting, and
review/CI requirements for the main branch. These are repository settings,
not claims of existing GitHub approval or completed hosted checks. Review the
Git commit identity before the initial commit; no email or remote URL is
embedded in this package.

## Noctalia distribution scope

The catalog and directory layout follow Noctalia's
[source publishing guide](https://docs.noctalia.dev/noctalia/plugins/development/workflow/).
The native helper still needs a local build, which is handled by the installer.
A remote Git source alone cannot build it.

The current [community store rules](https://github.com/noctalia-dev/community-plugins#what-a-plugin-is-allowed-to-be)
reject external UI helpers. This version draws its black layer through a
native Wayland helper, so a store submission needs an architectural change,
such as using a suitable Noctalia-native layer API. This is a Noctalia store
restriction and does not prevent independent GitHub source distribution.
No community-store submission or GitHub publication is performed by these
preparation scripts.
