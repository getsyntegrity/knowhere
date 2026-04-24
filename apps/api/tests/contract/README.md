# API Contract Tests

Put endpoint specifications here.

Each test should describe:

- the request
- the visible response
- the resulting state change

Good examples:

- `test_should_create_a_new_guest_device_when_posting_a_fresh_device_id`
- `test_should_return_429_when_job_creation_limit_is_exceeded`

Bad examples:

- tests that call route functions directly
- tests that assert which repository method was called
- tests that patch the service being verified
