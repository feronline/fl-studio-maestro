"""`fl-maestro` command: install the FL Studio side, check the connection, run the server."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__, paths
from .bridge import Bridge, BridgeError, from_fl_port, to_fl_port

STEPS = """
Next steps (once):
  1. loopMIDI (https://www.tobias-erichsen.de/software/loopmidi.html): create TWO ports named exactly
     "Maestro" and "Maestro Reply". (macOS: two IAC Driver buses with those names.)
  2. Restart FL Studio and open Options > MIDI settings:
       Input  "Maestro"       -> Enable, Controller type "Maestro Bridge", Port 10
       Output "Maestro Reply" -> Port 10 (the same number)
     View > Script output should say: Maestro Bridge ... ready (SysEx). Reply output linked: yes
  3. Run `fl-maestro doctor` to check the connection.
"""


def setup(fl_dir: Path | None) -> int:
    base = fl_dir or paths.fl_user_dir()
    if not base.exists():
        print(f"FL Studio user folder not found: {base}\n"
              "Open FL Studio once, or pass --fl-dir (Options > File settings > User data folder).")
        return 1
    target = base / "Settings" / "Hardware" / "Maestro Bridge"
    target.mkdir(parents=True, exist_ok=True)
    src = resources.files("fl_maestro") / "fl_scripts" / "device_MaestroBridge.py"
    with resources.as_file(src) as path:
        shutil.copyfile(path, target / "device_MaestroBridge.py")
    rolls = base / "Settings" / "Piano roll scripts"
    rolls.mkdir(parents=True, exist_ok=True)
    print(f"Installed the device script: {target / 'device_MaestroBridge.py'}")
    print(f"Piano roll scripts will be written to: {rolls}")
    print(STEPS)
    return 0


def doctor() -> int:
    print(f"fl-studio-maestro {__version__}")
    print(f"FL user folder: {paths.fl_user_dir()} ({'found' if paths.fl_user_dir().exists() else 'missing'})")
    script = paths.hardware_dir() / "Maestro Bridge" / "device_MaestroBridge.py"
    print(f"Device script:  {script} ({'installed' if script.exists() else 'missing: run fl-maestro setup'})")
    print(f"Projects:       {paths.projects_root()}")
    try:
        from . import midiports
        outs, ins = midiports.output_names(), midiports.input_names()
        print(f"MIDI outputs:   {', '.join(outs) or 'none'}")
        print(f"MIDI inputs:    {', '.join(ins) or 'none'}")
        for want, have, kind in ((to_fl_port(), outs, "output"), (from_fl_port(), ins, "input")):
            if want not in have:
                print(f"  ! no MIDI {kind} named {want!r}: create it in loopMIDI")
    except Exception as exc:
        print(f"MIDI ports:     cannot list ({exc})")
    try:
        info = Bridge(timeout=2).call("ping")
    except BridgeError as exc:
        print(f"Bridge:         not connected\n\n{exc}")
        return 1
    print(f"Bridge:         connected (FL {info.get('fl_version')}, tempo {info.get('tempo')}, "
          f"{info.get('channels')} channels)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fl-maestro", description="FL Studio Maestro: multi-agent music production for FL Studio.")
    parser.add_argument("--version", action="version", version=f"fl-studio-maestro {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_setup = sub.add_parser("setup", help="Install the Maestro Bridge script into FL Studio")
    p_setup.add_argument("--fl-dir", type=Path, help="FL Studio user data folder (default: Documents/Image-Line/FL Studio)")
    sub.add_parser("doctor", help="Check the installation and the live connection")
    sub.add_parser("serve", help="Run the MCP server on stdio")
    args = parser.parse_args(argv)
    if args.cmd == "setup":
        return setup(args.fl_dir)
    if args.cmd == "doctor":
        return doctor()
    from .server import main as serve
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
