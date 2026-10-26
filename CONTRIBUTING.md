# Contributing

Use a focused issue or pull request describing the user-visible problem and
reproduction steps. Please keep discussions respectful and relevant.

Build and check a working copy:

```sh
python3 -B -m unittest discover -s screen-blackout/tests -v
python3 -B -m unittest discover -s tests -v
CFLAGS="-Werror -fanalyzer" screen-blackout/build-helper.sh
python3 -B scripts/check_project.py
python3 -B scripts/release.py
```

Some publication checks use Git's tracked-file list. Stage new intended source
files before running them; do not stage build outputs or private files.
Tests run against temporary files and simulated compositor replies, with no
need for an active Wayland session. Test the installed plugin manually on one
monitor with a recovery route available after changing Wayland/input behavior.

Keep the manifest and catalog versions and metadata aligned. Use an entry API
only if it is available at the declared Noctalia plugin API level. Do not
introduce hard-coded monitor names, personal paths, or a mandatory network
service. State which display behavior was actually observed during testing.

Contributors must have permission to submit their changes and retain all
third-party attribution. Contributions to original project files use this
project's MIT licence. AI-assisted contributions are welcome when the
contributor understands, reviews, tests, and can account for the submitted code.
Report vulnerabilities according to SECURITY.md.
