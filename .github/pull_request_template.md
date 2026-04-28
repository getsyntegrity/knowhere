## Summary

- describe the change
- describe any API, worker, deployment, or migration impact
- link the related issue or task

## Verification

- list the commands you ran
- list any manual API, worker, or local-dev checks you performed
- note anything intentionally not tested

## Deployment Notes

- note new or changed environment variables
- note database migrations, queue changes, storage changes, or release-order requirements
- note backwards compatibility or rollback concerns

## Checklist

- [ ] Tests were added or updated when behavior changed
- [ ] Public docs, examples, or OpenAPI contracts were updated when needed
- [ ] Database migrations are idempotent and safe to deploy
- [ ] Logs, errors, and validation paths avoid leaking secrets or user data
- [ ] The pull request description explains any breaking or user-visible change
