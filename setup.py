from setuptools import setup, find_packages

setup(
    name="exmldoc",
    version="1.0.0",
    author='Yannick Versley',
    author_email='yversley@gmail.com',
    install_requires=[
        'regex',
        'isounidecode',
        ''
    ],
    license='LGPLv3',
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Text Processing :: Linguistic'],
    package_dir = {'': 'py_src'},
    packages=find_packages('py_src'),
    entry_points={
        'console_scripts': [
            'exml2cqp = exmldoc.exml2cqp:main'
        ]
    }
)
