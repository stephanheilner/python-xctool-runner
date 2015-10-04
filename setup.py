from distutils.core import setup

setup(
    name='python-xctool-runner',
    version='1.0.0dev',
    packages=['xctool_runner'],
    entry_points=dict(
        console_scripts=[
              'xctool-runner = xctool_runner.__main__:main'
        ],
    ),
    license='MIT',
    description='Lets you run tests with retries and/or partitioned across multiple sessions.',
    long_description=open('README.md').read(),
    install_requires=[
    ],
)
