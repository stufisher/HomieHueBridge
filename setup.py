#!/usr/bin/env python
from setuptools import setup, find_packages


def main():
    setup(
        name="HomieHueBridge",
        package_dir={"homie_hue_bridge": "homie_hue_bridge"},
        python_requires=">=3.6",
        install_requires=["setuptools", "homie", "requests"],
        packages=find_packages(),
        version="1.0.0",
        entry_points={
            "console_scripts": [
                "homie-hue-bridge = homie_hue_bridge.HomieHueBridge:main"
            ]
        },
    )


if __name__ == "__main__":
    main()
