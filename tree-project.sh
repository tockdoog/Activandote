#!/bin/bash

TARGET_DIR="${1:-.}"

find "$TARGET_DIR" \
\( \
-name node_modules -o \
-name .git -o \
-name dist -o \
-name build -o \
-name coverage -o \
-name .next -o \
-name venv -o \
-name __pycache__ -o \
-name .idea -o \
-name .vscode \
\) -prune \
-o -print