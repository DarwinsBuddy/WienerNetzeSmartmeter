---
paths:
  - "**/*.py"
---

# Typing

- Use the strictest type that a value actually has. Do not use `Any` or a wider type when a stricter one exists.
- Do not make a type stricter than the value actually is.

## External libraries

- Do not guess the types of an external interface. Read the signature in the installed source (`.venv/Lib/site-packages/` on Windows, `.venv/lib/python3.*/site-packages/` on Linux and macOS).
- Use the exact types that the library declares for decorators, public SDK methods, parameters and return values. Do not make them wider, and do not replace them with stricter types of your own.
