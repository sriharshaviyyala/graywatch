# Contributing to GrayWatch

Thanks for the interest. Ground rules that keep this tool trustworthy:

1. **Read-only is non-negotiable.** No contribution may add any code path
   that writes to, configures, or authenticates against a network device.
   GrayWatch finds the liar; it never touches the network.
2. **Zero dependencies stays zero.** Standard library only. If a feature
   needs a dependency, it belongs in a separate integration, not here.
3. **Statistics must stay auditable.** Confidence math must be explainable
   to a skeptical network architect in a paragraph. Exact methods over
   opaque scores.
4. **Determinism.** Same input → same verdict, same odds. Seed anything
   random.
5. **Tests with claims.** A bug fix comes with the test that would have
   caught it; a feature comes with tests for its honest failure modes.

War stories welcome: if GrayWatch convicted (or missed) a real gray failure
on your fabric, an anonymized probe set makes the best possible issue.

By contributing you agree your contributions are licensed under Apache-2.0.
