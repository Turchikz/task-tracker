#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

version="$(tr -d '\r\n' < VERSION)"
test -n "$version"

if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is not clean:" >&2
    git status --short >&2
    exit 1
fi

tag="v$version"

if git rev-parse "$tag" >/dev/null 2>&1; then
    echo "Tag $tag already exists." >&2
    exit 1
fi

git tag -a "$tag" -m "Task Tracker $tag"

echo "Tag $tag created locally."
echo "Push it with:"
echo "  git push origin $tag"
