# AWS utilities

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![PyPI - Version](https://img.shields.io/pypi/v/aws-python-boto-tools)
![CI](https://github.com/satyap/aws-python-boto-tools/actions/workflows/ci.yml/badge.svg)

A collection of Python packages for:

* [Sending SQS messages in batches (efficient for cost and compute)](README_sqs_send_batch.md)
* [Using STS assume-role with an in-memory LRU cache](README_sts_assume_role.md)

---

## Testing

`make test`

* Uses moto to mock AWS SQS
* Type-checked with mypy: mypy src tests

---

## Development & Contributing

* Fork the repo
* Create a feature branch
* Write tests for new functionality
* Submit a pull request

---

## License

See the [LICENSE](LICENSE) file for details

---
