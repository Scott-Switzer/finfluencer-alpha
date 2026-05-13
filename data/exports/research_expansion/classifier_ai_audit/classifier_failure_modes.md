# Classifier Failure Modes

1. **Ambiguous ticker context**: Rule labels may miss negated or third-party mentions.
2. **Portfolio vs. recommendation**: Rules sometimes conflate 'I own this' with 'buy this'.
3. **Historical vs. current**: Past-tense purchases may be misclassified as current recommendations.
4. **Direction mismatch**: Price targets without directional language default to neutral.
5. **Low-confidence events**: Events with short evidence windows are often unclear.