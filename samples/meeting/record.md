# Meeting record

## Summary

The team discussed the Kubernetes memory issue and planned to migrate the PostgreSQL database to a managed instance by Friday. They considered switching the CI/CD pipeline to GitHub Actions but postponed the decision. They decided to implement OAuth with JWT tokens for the new login API. An open need was identified to update the Swagger documentation.

## Minutes

### Kubernetes memory issue and DB migration

- Kubernetes cluster runs out of memory
- Plan to move PostgreSQL to a managed instance
- Deadline set for Friday

### CI/CD pipeline proposal

- Arjun proposed switching from Jenkins to GitHub Actions
- Decision postponed; to discuss next week

### Authentication decision

- Decided to use OAuth with JWT tokens for the new login API

### Swagger documentation update

- Need to update the Swagger docs
- No volunteer yet

## Key decisions

1. Use OAuth with JWT tokens for the new login API _(00:22: "We decided to use OAuth with JWT tokens for the new login API.")_

## Action items

| # | Task | Owner | Deadline | Source |
|---|------|-------|----------|--------|
| 1 | Move PostgreSQL database to a managed instance | Priya | by Friday | 00:07 |
| 2 | Update Swagger documentation | Unspecified | Unspecified | 00:27 |

## Open proposals and questions

- **Proposal, raised by Arjun:** Switch CI/CD pipeline from Jenkins to GitHub Actions _(00:13: "Arjun proposed switching our CI/CD pipeline from Jenkins to GitHub Actions,")_
