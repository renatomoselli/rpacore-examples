#!/usr/bin/env bash
set -euo pipefail

# Configure git identity (required on systems without global config)
git config --global user.email "test@test.com"
git config --global user.name "Test"

# Create healthy repo (alpha)
mkdir -p sample_repos/alpha
cd sample_repos/alpha
git init
echo "Hello World" > README.md
git add README.md
git commit -m "Initial commit"
git remote add origin https://github.com/example/alpha.git

# Create degraded repo (beta)
mkdir -p sample_repos/beta
cd ../beta
git init
echo "Beta Project" > README.md
git add README.md
git commit -m "Initial commit"

# Create a stale branch
git checkout -b feature-old
echo "Old feature" > old_feature.txt
git add old_feature.txt
GIT_AUTHOR_DATE="2023-01-15T12:00:00+00:00" \
GIT_COMMITTER_DATE="2023-01-15T12:00:00+00:00" \
  git commit -m "Old feature work"

# Go back to main, leave a stale branch
git checkout -

# Create uncommitted changes
echo "Uncommitted" > uncommitted.txt
