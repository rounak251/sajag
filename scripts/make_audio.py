"""Record the sample IVR messages with macOS text-to-speech. Needs the Lekha and Rishi voices.

Lekha is a Hindi voice, so Maithili and Bhojpuri audio is Hindi-accented: a stand-in until a
native speaker records them.
"""
import subprocess
import tempfile
from pathlib import Path

from sajag import alerts as A
from sajag.config import WEB

SAMPLE_DISTRICT, SAMPLE_DAYS = "darbhanga", 3
VOICES = {"hi": "Lekha", "mai": "Lekha", "bho": "Lekha", "en": "Rishi"}


def main() -> None:
    out = WEB / "data" / "audio"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for language, voice in VOICES.items():
            for level in (1, 2, 3):
                text = A.render(language, level, SAMPLE_DISTRICT, SAMPLE_DAYS, "voice")
                aiff = Path(tmp) / "x.aiff"
                subprocess.run(["say", "-v", voice, "-r", "150", "-o", str(aiff), text], check=True)
                target = out / f"{language}_{level}.m4a"
                subprocess.run(
                    ["afconvert", "-f", "m4af", "-d", "aac", "-b", "48000", str(aiff), str(target)],
                    check=True,
                )
                print(target.name, target.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
