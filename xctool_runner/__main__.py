import argparse
import json
import os
import sys
from . import TimeoutError, run_script


def main():
    parser = argparse.ArgumentParser(description='Run tests.')
    parser.add_argument('action', nargs='+', choices=['build', 'test'])
    parser.add_argument('--workspace', required=True, help='Workspace to build and test.')
    parser.add_argument('--scheme', required=True, help='Scheme to build and test.')
    parser.add_argument('--target', required=True, help='Test target.')
    parser.add_argument('--retries', type=int, default=4, help='The maximum number of times to retry a set of tests without progress.')
    parser.add_argument('--timeout', type=int, default=120, help='The number of seconds to wait without output before failing a test run.')
    parser.add_argument('--partition', type=int, default=0, help='The partition index to run.')
    parser.add_argument('--partition-count', dest='partition_count', type=int, default=1, help='The total number of partitions.')
    parser.add_argument('--devices', default='iPhone 5,9.0;iPad 2,9.0')
    args = parser.parse_args()

    xctool_path = '/usr/local/bin/xctool'

    build_path = os.path.abspath('build')
    try:
        os.makedirs(build_path)
    except:
        pass

    for action in args.action:
        if action == 'build':
            build_tests(xctool_path=xctool_path, workspace=args.workspace, scheme=args.scheme, target=args.target, build_path=build_path, timeout=args.timeout)
        elif action == 'test':
            run_tests(xctool_path=xctool_path, workspace=args.workspace, scheme=args.scheme, target=args.target, build_path=build_path, partition=args.partition, partition_count=args.partition_count, devices=parse_devices(args.devices), retries=args.retries, timeout=args.timeout)


def print_message(message):
    message = 'xctool-runner: ' + message
    print '=' * len(message)
    print message
    print '=' * len(message)
    sys.stdout.flush()


def parse_devices(string):
    devices = []
    for name, version in [device_spec.split(',', 1) for device_spec in string.split(';')]:
        devices.append(dict(
            destination='platform=iOS Simulator,OS={version},name={name}'.format(version=version, name=name),
            description='{name} / iOS {version}'.format(version=version, name=name),
            name=name,
            version=version,
        ))

    return devices


def build_tests(xctool_path, workspace, scheme, build_path, target, timeout):
    print_message('Building tests')

    try:
        script = '{xctool_path} -workspace "{workspace}" -scheme "{scheme}" -sdk iphonesimulator CONFIGURATION_BUILD_DIR="{build_path}" -derivedDataPath="{build_path}" build-tests -only {target} -reporter pretty'.format(
                xctool_path=xctool_path,
                workspace=workspace,
                scheme=scheme,
                build_path=build_path,
                target=target,
            )
        print script
        script_result, _ = run_script(script, timeout)

        if script_result != 0:
            print_message('Failed to build tests')
            exit(1)

    except TimeoutError:
        print_message('Timed out building tests')
        exit(1)


def get_all_tests(xctool_path, workspace, scheme, build_path, target, timeout):
    print_message('Listing tests')

    stream_json_path = os.path.join(build_path, 'stream.json')

    try:
        script = '{xctool_path} -workspace "{workspace}" -scheme "{scheme}" -sdk iphonesimulator CONFIGURATION_BUILD_DIR="{build_path}" -derivedDataPath="{build_path}" run-tests -listTestsOnly -only {target} -reporter pretty -reporter json-stream:{stream_json_path}'.format(
                xctool_path=xctool_path,
                workspace=workspace,
                scheme=scheme,
                build_path=build_path,
                target=target,
                stream_json_path=stream_json_path,
            )
        print script
        script_result, _ = run_script(script, timeout)

        if script_result != 0:
            print_message('Failed to list tests')
            exit(1)

    except TimeoutError:
        print_message('Timed out listing tests')
        exit(1)

    tests = []
    with open(stream_json_path) as f:
        for line in f.readlines():
            event = json.loads(line)
            if event['event'] == 'begin-test':
                tests.append(dict(
                    class_name=event['className'],
                    method_name=event['methodName'],
                ))

    return tests


def get_partitions(elements, count):
    partitions = []

    division = float(len(elements)) / float(count)
    for i in xrange(0, count):
        start = int(round(division * float(i)))
        end = int(round(division * float(i + 1)))
        partition = elements[start:end]
        partitions.append(partition)

    return partitions


def run_tests(xctool_path, workspace, scheme, build_path, target, partition, partition_count, devices, retries, timeout):
    tests = get_all_tests(xctool_path=xctool_path, workspace=workspace, scheme=scheme, build_path=build_path, target=target, timeout=timeout)

    print_message('Got list of tests')

    partitions = get_partitions(tests, partition_count)
    partitioned_tests = partitions[partition]
    for test in tests:
        marker = '>' if test in partitioned_tests else ' '
        print '\t{marker} {class_name}.{method_name}'.format(marker=marker, class_name=test['class_name'], method_name=test['method_name'])

    for device in devices:
        attempt = 1

        remaining_tests = partitioned_tests
        while remaining_tests and attempt <= retries + 1:
            attempt_description = 'attempt {attempt}'.format(attempt=attempt)

            print_message('Running {test_count} test(s) on {device_description} ({attempt_description})'.format(test_count=len(remaining_tests), device_description=device['description'], attempt_description=attempt_description))

            for test in remaining_tests:
                print '\t> {class_name}.{method_name}'.format(class_name=test['class_name'], method_name=test['method_name'])

            stream_json_path = os.path.join(build_path, 'stream.json')
            try:
                os.remove(stream_json_path)
            except:
                pass

            try:
                script = '{xctool_path} -workspace "{workspace}" -scheme "{scheme}" -sdk iphonesimulator -destination "{destination}" CONFIGURATION_BUILD_DIR="{build_path}" -derivedDataPath="{build_path}" run-tests -freshSimulator -resetSimulator -only {target} -reporter pretty -reporter json-stream:{stream_json_path}'.format(
                        xctool_path=xctool_path,
                        workspace=workspace,
                        scheme=scheme,
                        destination=device['destination'],
                        build_path=build_path,
                        target='{target}:{tests}'.format(target=target, tests=','.join(['{}/{}'.format(test['class_name'], test['method_name']) for test in remaining_tests])),
                        stream_json_path=stream_json_path,
                    )
                print script
                run_script(script, timeout)

            except TimeoutError:
                print_message('Timed out running tests')

            failed_tests = list(remaining_tests)
            with open(stream_json_path) as f:
                for line in f.readlines():
                    event = json.loads(line)
                    if event['event'] == 'end-test' and event['succeeded'] == True:
                        failed_tests.remove(dict(
                            class_name=event['className'],
                            method_name=event['methodName'],
                        ))

            if failed_tests:
                print_message('{failure_count} of {test_count} test(s) FAILED on {device_description} ({attempt_description})'.format(failure_count=len(failed_tests), test_count=len(remaining_tests), device_description=device['description'], attempt_description=attempt_description))

            if len(failed_tests) < len(remaining_tests):
                attempt = 1
            else:
                attempt += 1

            remaining_tests = failed_tests

        if remaining_tests:
            print_message('Tests FAILED on {device_description} too many times without progress'.format(device_description=device['description']))
            exit(1)

        print_message('Tests PASSED on {device_description}'.format(device_description=device['description']))

    print_message('All tests PASSED on all devices')
