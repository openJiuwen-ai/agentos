"""IAM layer — unified auth (tokens, permissions, security deps).

Backend-agnostic: consumes ``AbstractUserBackend``, never touches ORM models
directly (except ``UserRevocation`` which is IAM infrastructure).
"""
