# Meeting record

## Summary

The team began sprint planning and addressed a Kubernetes memory issue, planning to migrate PostgreSQL to a managed instance by Friday. They discussed a proposal to switch the CI/CD pipeline from Jenkins to GitHub Actions, which will be revisited next week. A decision was made to use OAuth with JWT tokens for the new login API, and the need to update the Swagger documentation was noted.

## Minutes

### Kubernetes memory issue & DB migration

- Kubernetes cluster runs out of memory
- Move PostgreSQL to a managed instance by Friday

### CI/CD pipeline proposal

- Switch CI/CD from Jenkins to GitHub Actions

### Authentication decision

- Use OAuth with JWT tokens for new login API

### Swagger documentation

- Update Swagger docs needed

## Key decisions

1. Use OAuth with JWT tokens for the new login API _(00:22: "We decided to use OAuth with JWT tokens for the new login API.")_

## Action items

| # | Task | Owner | Deadline | Source |
|---|------|-------|----------|--------|
| 1 | Move the PostgreSQL database to a managed instance | Priya | by Friday | 00:07 |
| 2 | Update the Swagger docs | Unspecified | Unspecified | 00:27 |

## Open proposals and questions

- **Proposal, raised by Arjun:** Switch CI/CD pipeline from Jenkins to GitHub Actions _(00:13: "Arjun proposed switching our CI/CD pipeline from Jenkins to GitHub Actions,")_
