$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot

git remote set-url origin 'https://github.com/SYNTEC-20101749/-.git'
git add --all
git commit -m 'Release v1.0.6: upload selection and settings dialogs'
git push origin HEAD
git tag -a v1.0.6 -m 'Release v1.0.6'
git push origin v1.0.6
