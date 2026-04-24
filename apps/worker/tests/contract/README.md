# Worker Contract Tests

Put worker surface specifications here.

These tests should verify:

- task entrypoint behavior
- durable side effects
- queue-facing or task-facing contracts

These tests should avoid:

- asserting helper call sequences
- patching internal services that define the behavior under test
- turning task tests into unit tests disguised as contracts
