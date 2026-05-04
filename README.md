# payload-manager

A GTK4 payload manager for penetration testers. Organise payloads by category, click to copy to clipboard instantly — no terminal required.

Built for Wayland (uses `wl-copy`).

---

## Requirements

- Python 3
- GTK4 + PyGObject (`python-gobject`)
- `wl-copy` (`wl-clipboard`)

### Arch / CachyOS

```bash
sudo pacman -S python-gobject wl-clipboard
```

### Debian / Ubuntu

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 wl-clipboard
```

---

## Installation

```bash
git clone https://github.com/Galatron01/payload-manager.git
cd payload-manager
bash install.sh
```

---

## Usage

```bash
payload-manager
```

Or bind it to a key in your compositor config.

### Niri

```
binds {
    Mod+P { spawn "payload-manager"; }
}
```

---

## How it works

- **Left panel** — categories (each is a `.txt` file in `~/payloads/`)
- **Right panel** — payloads for the selected category
- **Click a payload** — copies instantly to clipboard via `wl-copy`
- **Add payload** — type in the box at the bottom, press Enter
- **Delete** — select a payload and click Delete Selected
- **Search** — filter bar top right
- **+ Category** — creates a new category

Payloads are stored as plain text files in `~/payloads/<category>.txt`, one payload per line. Edit them directly in any text editor or Obsidian.

---

## Adding your own payloads

Drop a `.txt` file into `~/payloads/` — one payload per line. It'll appear as a category automatically on next launch.
