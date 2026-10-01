"""Week 11: the Java adapter. Parse to IR with file:line provenance, diff by entity, JCA crypto tagging."""

from pathlib import Path

import pytest

from changeproof.adapters.base import ChangeKind
from changeproof.adapters.java import JavaAdapter, JavaSyntaxError

SYSTEM = Path(__file__).resolve().parent / "fixtures" / "java" / "system"
PKG = "src/main/java/com/example/pay"


def parse(rel, root=SYSTEM):
    return JavaAdapter().parse(root / rel, root)


def by_id(module):
    return {e.id: e for e in module.entities}


def line_of(rel, text):
    return next(n for n, line in enumerate((SYSTEM / rel).read_text().splitlines(), 1) if text in line)


def test_types_methods_and_fields_carry_their_lines():
    rel = f"{PKG}/core/FeeCalculator.java"
    found = by_id(parse(rel))
    fee = found["method:com.example.pay.core.FeeCalculator.fee(long)"]
    assert (fee.provenance.file, fee.provenance.line) == (rel, line_of(rel, "public static long fee"))
    assert fee.provenance.end_line == fee.provenance.line + 3
    assert fee.attributes["scope"] == "class:com.example.pay.core.FeeCalculator"
    rate = found["field:com.example.pay.core.FeeCalculator.RATE_BASIS_POINTS"]
    assert rate.provenance.line == line_of(rel, "RATE_BASIS_POINTS =") and rate.attributes["type"] == "long"
    assert found["class:com.example.pay.core.FeeCalculator"].attributes["type_kind"] == "class"
    assert "method:com.example.pay.core.FeeCalculator.<init>()" in found


def test_records_constructors_inheritance_and_imports():
    found = by_id(parse(f"{PKG}/core/RecurringPaymentService.java"))
    recurring = found["class:com.example.pay.core.RecurringPaymentService"]
    assert recurring.attributes["extends"] == ["PaymentService"]
    assert "method:com.example.pay.core.RecurringPaymentService.<init>(Ledger,ReceiptSigner)" in found
    imports = [e for e in found.values() if e.kind == "import"]
    assert [e.name for e in imports] == ["com.example.pay.crypto.ReceiptSigner"]
    payment = by_id(parse(f"{PKG}/core/Payment.java"))["class:com.example.pay.core.Payment"]
    assert payment.attributes["type_kind"] == "record"


def test_calls_and_field_uses_name_the_method_they_are_in():
    rel = f"{PKG}/core/PaymentService.java"
    module = parse(rel)
    pay = "method:com.example.pay.core.PaymentService.pay(Payment)"
    calls = [e for e in module.entities if e.kind == "call" and e.attributes["scope"] == pay]
    assert [(c.name, c.attributes["receiver"]) for c in calls] == [
        ("fee", "FeeCalculator"), ("amount", "payment"), ("post", "ledger"), ("amount", "payment"),
        ("sign", "signer"), ("id", "payment")]
    assert all(c.provenance.file == rel for c in calls)
    assert calls[2].provenance.line == line_of(rel, "ledger.post(")
    uses = {e.attributes["field"] for e in module.entities if e.kind == "field-ref" and e.attributes["scope"] == pay}
    assert uses == {"ledger", "signer"}


def test_jca_calls_are_tagged_with_their_algorithm():
    rel = f"{PKG}/crypto/ReceiptSigner.java"
    crypto = [e for e in parse(rel).entities if e.kind == "crypto-call"]
    assert [(c.attributes["service"], c.attributes["algorithm"], c.attributes["quantum_vulnerable"]) for c in crypto] == [
        ("java.security.KeyPairGenerator", "ml-dsa", False), ("java.security.Signature", "ml-dsa", False)]
    assert crypto[0].provenance.line == line_of(rel, "KeyPairGenerator.getInstance")
    digest = [e for e in parse(f"{PKG}/crypto/ReceiptDigest.java").entities if e.kind == "crypto-call"]
    assert [(c.attributes["category"], c.attributes["algorithm"]) for c in digest] == [("hash", "sha-384")]


def test_rsa_with_a_key_size_reads_as_quantum_vulnerable(tmp_path):
    rel = "Keys.java"
    (tmp_path / rel).write_text("""import java.security.*;
class Keys {
    KeyPair make() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(3072);
        return g.generateKeyPair();
    }
    Signature sig() throws Exception { return Signature.getInstance("SHA256withECDSA"); }
    javax.crypto.Cipher c() throws Exception { return javax.crypto.Cipher.getInstance("AES/GCM/NoPadding"); }
}
""")
    crypto = [e.attributes for e in parse(rel, tmp_path).entities if e.kind == "crypto-call"]
    assert [(c["algorithm"], c["key_bits"], c["quantum_vulnerable"]) for c in crypto] == [
        ("rsa", 3072, True), ("ecc", None, True), ("aes", None, False)]


def test_a_comment_or_a_moved_line_is_not_a_change(tmp_path):
    rel = f"{PKG}/core/FeeCalculator.java"
    source = (SYSTEM / rel).read_text()
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text(source.replace("        long fee = amount", "        // basis points\n\n        long fee = amount"))
    adapter = JavaAdapter()
    assert adapter.diff(parse(rel), parse(rel, tmp_path)) == []
    (tmp_path / rel).write_text(source.replace("/ 10000", "/ 1000"))
    changed = adapter.diff(parse(rel), parse(rel, tmp_path))
    assert [(c.change, c.entity.id) for c in changed] == [
        (ChangeKind.MODIFIED, "method:com.example.pay.core.FeeCalculator.fee(long)")]


def test_ids_never_hold_a_line_number_and_every_fact_has_provenance():
    for path in sorted(SYSTEM.rglob("*.java")):
        rel = path.relative_to(SYSTEM).as_posix()
        for e in parse(rel).entities:
            assert e.provenance.file == rel and e.provenance.line >= 1
            assert str(e.provenance.line) not in e.id.split("#")[0].split("(")[0].split(".")[-1]


def test_broken_java_is_refused_with_its_line(tmp_path):
    (tmp_path / "Bad.java").write_text("class Bad {\n  void m() {\n    int x = ;\n  }\n}\n")
    with pytest.raises(JavaSyntaxError) as found:
        parse("Bad.java", tmp_path)
    assert found.value.errors[0][0].line == 3


def test_running_java_is_planned():
    with pytest.raises(NotImplementedError, match="planned"):
        JavaAdapter().run(parse(f"{PKG}/core/Ledger.java"), {})
