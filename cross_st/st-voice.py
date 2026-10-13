#!/usr/bin/env python3
"""
## st-voice — Browse, download, and test Piper TTS voice models

Three modes of use:

  Browse   — list all available en_US / en_GB Piper voice names:
               st-voice --voices

  Download — print curl commands to fetch ONNX model files from Hugging Face;
             pipe directly to bash to download them all at once:
               st-voice --curl | bash

  Test     — interactive shell for auditioning voices on a .txt file:
               st-voice sample.txt

Interactive commands at the prompt:
  q quit  e edit  f filter-for-TTS  s speak  v next-voice  k kill-grip  ? help

The interactive V key in st-admin opens this tool.  Once you have found the
right voice, save it with:
  st-admin --set-tts-voice en_US-lessac-medium

For local Kokoro, set TTS_BACKEND=kokoro and TTS_VOICE=af_heart.
Kokoro auditioning uses the configured voice; voice browsing is for Piper.
Use st-speak to render a full report container to MP3 with the saved voice.

TTS is optional — without it, use requirements-no-tts.txt and Python 3.10+.
With TTS, Python 3.10–3.13 all work (soundfile and yakyak have wheels for
every supported Python version on macOS ARM and Linux).

See also: st-admin (set default TTS voice)
          st-speak  (render a story container to MP3)
"""

import argparse
import os
import subprocess
import sys
import time
from mmd_startup import load_cross_env, require_config

from _tts import get_backend, get_voice, render_audio

from mmd_for_speaking import for_speaking
from mmd_voice import get_onyx_voice_list, get_onyx_voice_curl, get_onyx_voice_list_best_few


def render_voice(text_content, file_mp3, host, port, voice, verbose):
    return render_audio(text_content, file_mp3, voice, host=host, port=port,
                        verbose=verbose)


def find_and_kill_process(port):
    try:
        # Find processes using the port
        result = subprocess.run(
            ["lsof", "-i", f":{port}"],
            capture_output=True, text=True
        )

        # Parse PIDs from the output
        lines = result.stdout.splitlines()
        pids = {line.split()[1] for line in lines[1:] if len(line.split()) > 1}

        if pids:
            print(f"Killing processes using port {port}: {', '.join(pids)}")
            for pid in pids:
                subprocess.run(["sudo", "kill", "-9", pid], check=True)
            print("Processes killed successfully.")
        else:
            print(f"No processes found using port {port}.")

    except Exception as e:
        print(f"Error: {e}")


def main():
    require_config()
    parser = argparse.ArgumentParser(
        prog='st-voice',
        description='Rapid testing of spoken audio.')
    parser.add_argument('text_file', type=str, nargs='?', default=None,
                        help='Path to a text file (optional)', metavar='file.txt')
    parser.add_argument('-voices', '--voices', action='store_true',
                        help='Print names of all onyx voices, default: off')
    parser.add_argument('-curl', '--curl', action='store_true',
                        help='Print curl commands to download all onyx voices, default: off')
    parser.add_argument('-k', '--kill', action='store_true',
                        help='Kill gimp server on port 6419, default is do not kill')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output, default is verbose')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Enable minimal output')

    args = parser.parse_args()

    if args.voices:
        voice_list = get_onyx_voice_list()
        print('\n'.join(voice_list))
        sys.exit(0)

    if args.curl:
        curl_list = get_onyx_voice_curl()
        print('\n'.join(curl_list))
        sys.exit(0)

    if args.kill:
        find_and_kill_process(6419)
        sys.exit(0)

    if args.text_file is None:
        print("No file.txt, nothing to do")
        sys.exit(1)

    file_prefix = args.text_file.rsplit('.', 1)[0]  # Split from the right, only once
    file_txt = file_prefix + ".txt"
    file_mp3 = file_prefix + ".mp3"

    # Use realpath to get the actual path of the script
    load_cross_env()

    tts_voice = get_voice()

    try:
        if not os.path.isfile(file_txt):
            print(f"Error: The file {args.txt_file} does not exist.")
            sys.exit(1)

        with open(file_txt, 'r') as infile:
            text_content = infile.read()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    voice_opt = ([tts_voice] if get_backend() == "kokoro"
                 else get_onyx_voice_list_best_few())
    voice_select = 0

    def get_state():
        return f"voice:{tts_voice}"

    # valid commands, must match order of the apps list (up to help)
    valid_cmd = ['q', 'e', 'f', 's', 'v', 'k', '?']

    def update_next_app():
        apps = [
            "quit",
            f"vi {file_txt}",
            f"filter text for_speaking(text)",
            f"yakyak --backend {get_backend()} -i {file_txt} -f mp3 -v {tts_voice} -o {file_mp3}",
            f"next voice",
            f"kill lame gimp server on port 6419",
            f"help",
        ]
        return apps

    def print_menu():
        print(f"\nst-voice {get_state()} commands:")
        for i, app in enumerate(next_app):
            print(f" {valid_cmd[i]}- {app}")

    next_app = update_next_app()
    print_menu()
    grip_process = None

    while True:
        selection = input(f"\nst-voice {get_state()} cmd? ").strip()
        if selection not in valid_cmd:
            print("Invalid command. Please select command from the list.")
            continue

        match selection:
            case 'e':  # Edit
                cmd = [
                    "grip", "--browser", "--quiet",
                    f"--title={file_txt}",
                    file_txt
                ]
                # Do not start the process if it is already running
                if grip_process is None:
                    grip_process = subprocess.Popen(cmd, start_new_session=True)
                    time.sleep(1)  # Pause for grip message, otherwise it writes ontop of vi

                cmd = f"vi {file_txt}".split()
                subprocess.run(cmd)
                continue
            case 'f':  # filter text, mmd_for_speaking
                with open(file_txt, 'r') as infile:
                    text_content = infile.read()
                text_content = for_speaking(text_content, args.verbose)
                with open(file_txt, "w") as f:
                    f.write(text_content)
                continue
            case 's':  # render the mp3 with yakyak TTS + afplay
                with open(file_txt) as infile:
                    text_content = infile.read()
                if render_audio(text_content, file_mp3, tts_voice,
                                quiet=args.quiet, verbose=args.verbose):
                    subprocess.run(["afplay", file_mp3])
                continue
            case 'v':  # Switch to next voice
                voice_select = (voice_select + 1) % len(voice_opt)
                tts_voice = voice_opt[voice_select]
                next_app = update_next_app()
                continue
            case 'k':
                find_and_kill_process(6419)
                continue
            case 'q':
                # Don't kill the process if it is not running
                if grip_process is not None:
                    grip_process.terminate()
                    grip_process.wait()  # Ensure it stops completely
                    grip_process.kill()
                sys.exit(0)
            case '?':
                print_menu()
                continue


if __name__ == "__main__":
    main()
