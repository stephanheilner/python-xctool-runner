import os
import re
import signal
import subprocess
import sys
import tempfile
import time


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError
signal.signal(signal.SIGALRM, timeout_handler)


def run_script(script, timeout):
    print script
    sys.stdout.flush()

    try:
        # Create temporary files in which to store the script and output
        script_fd, script_path = tempfile.mkstemp()
        output_fd, output_path = tempfile.mkstemp()

        # Write out the script and make it executable
        with open(script_path, 'wb') as f:
            f.write(script)
        os.chmod(script_path, 0777)

        try:
            # Run the script and get the output, without garbling it or introducing buffer latency
            cmd = 'script -q -t 0 {output_path} {script_path}'.format(output_path=output_path, script_path=script_path)
            process = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)

            # Set the timeout
            signal.alarm(timeout)

            # Monitor the process and output
            previous_output_size = os.stat(output_path).st_size
            while process.poll() is None:
                # Check if there is any new output
                output_size = os.stat(output_path).st_size
                if previous_output_size != output_size:
                    previous_output_size = output_size

                    # Reset the timeout
                    signal.alarm(timeout)

                # Throttle polling
                time.sleep(1)

            # Deactivate the timeout
            signal.alarm(0)
        except TimeoutError as e:
            try:
                # Gently quit the script, then kill it with prejudice
                process.stdin.close()
                process.kill()
            except:
                pass
            raise e

        result = process.returncode

        # Read the output, stripping ANSI escape codes
        with open(output_path, 'r') as f:
            output = re.compile(r'\x1b[^m]*m').sub('', f.read())
    except Exception as e:
        raise e
    finally:
        # Close and remove the temporary files
        os.close(output_fd)
        os.close(script_fd)
        os.remove(output_path)
        os.remove(script_path)

    return result, output
