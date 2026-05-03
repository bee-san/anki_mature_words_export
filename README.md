# Bee's Anki Exporter

1. export all mature words in one click to clipboard
2. make yomitan freq dict out of it that auto updates

## Install In Anki

1. Open the latest GitHub release for this repo.
2. Download the `.ankiaddon` file from the release assets.
3. In Anki, go to `Tools` -> `Add-ons`.
4. Click `Install from file...`.
5. Select the downloaded `.ankiaddon` file.
6. Restart Anki when prompted.

## Use

After restart, use `Tools` -> `Export words`.

On first run, or whenever the add-on does not have a valid saved config yet, Anki will also show `Tools` -> `Set up Export words` so you can run the wizard.

## Reopen The Wizard

If you want to force the setup wizard to appear again, delete or clear the add-on's saved config and restart Anki. When the config is missing or invalid, the add-on shows `Tools` -> `Set up Export words` again.

The safest way to do that is:

1. In Anki, go to `Tools` -> `Add-ons`.
2. Select `Bee's Anki Exporter`.
3. Click `View Files`.
4. Close Anki.
5. Open `meta.json` in the add-on folder.
6. Delete the `"config"` section from that file, or delete `meta.json` entirely if you want a full reset.
7. Start Anki again.

After that, `Tools` -> `Set up Export words` should appear again.
