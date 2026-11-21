from decimal import Decimal

from django.test import SimpleTestCase

from payments.requisite_guard import BlockDecision, GuardConfig, Sample, decide_blocks, judge_detail, _spam_clients


def _cfg() -> GuardConfig:
    return GuardConfig()


def _deal(
    detail="A",
    *,
    trader="resdfe",
    merchant="aggrepay",
    client="u",
    success=False,
    recent=False,
    n=1,
    active=True,
):
    out = []
    for i in range(n):
        out.append(
            Sample(
                detail_id=detail,
                trader=trader,
                merchant=merchant,
                client=f"{client}-{i}" if n > 1 and client != "spam" else client,
                success=success,
                recent=recent,
                active=active,
                group_id=f"g-{detail}",
                label=detail,
            )
        )
    return out


def _unique(detail, n, **kwargs):
    """n deals, each its own client, so none of them is serial spam."""
    tag = kwargs.get("client_tag") or ("r" if kwargs.get("recent") else "o")
    if kwargs.get("success"):
        tag = f"{tag}s"
    rows = []
    for i in range(n):
        rows.extend(
            _deal(
                detail,
                client=f"{detail}-{tag}-c{i}-{kwargs.get('merchant', 'aggrepay')}",
                n=1,
                **kwargs,
            )
        )
    return rows


def _repeat(detail, client, n, **kwargs):
    return _deal(detail, client=client, n=1, **kwargs) * n


def _peers():
    """Two sibling cards that convert, same trader and merchant. Split across halves."""
    rows = []
    rows.extend(_unique("B", 8, success=False, recent=False))
    rows.extend(_unique("B", 6, success=True, recent=False))
    rows.extend(_unique("C", 6, success=False, recent=True))
    rows.extend(_unique("C", 6, success=True, recent=True))
    return rows


def _dead_card():
    """40 unpaid unique clients, 24 in the older half and 16 in the newer."""
    return _unique("A", 24, recent=False) + _unique("A", 16, recent=True)


class RequisiteGuardDecideTest(SimpleTestCase):
    def test_blocks_outlier_card_when_peers_and_merchant_pay(self):
        samples = _dead_card() + _peers()
        blocks = decide_blocks(samples, _cfg())
        self.assertEqual([b.detail_id for b in blocks], ["A"])
        self.assertEqual(blocks[0].raw_ok, 0)
        self.assertGreaterEqual(blocks[0].peer_ok, 1)

    def test_keeps_card_when_recent_half_pays(self):
        # 2/50 overall is still under 5%, but the fresh half is 2/10.
        samples = _unique("A", 40, recent=False)
        samples += _unique("A", 8, recent=True)
        samples += _unique("A", 2, success=True, recent=True)
        samples += _peers()
        self.assertEqual(decide_blocks(samples, _cfg()), [])
        spam = _spam_clients(samples, _cfg())
        self.assertEqual(judge_detail("A", samples, _cfg(), spam), "half-paid")

    def test_keeps_card_when_whole_team_is_dead(self):
        samples = _dead_card()
        samples += _unique("B", 20, recent=False) + _unique("B", 10, recent=True)
        samples += _unique("C", 15, recent=False) + _unique("C", 10, recent=True)
        self.assertEqual(decide_blocks(samples, _cfg()), [])

    def test_keeps_card_that_converts_for_another_merchant(self):
        samples = _dead_card() + _peers()
        samples += _unique("A", 3, merchant="melbet", success=True, trader="resdfe")
        self.assertEqual(decide_blocks(samples, _cfg()), [])

    def test_keeps_card_when_only_serial_spam_remains(self):
        samples = []
        for i in range(6):
            samples.extend(_repeat("A", f"spam{i}", 5, success=False, recent=(i >= 3)))
        samples += _peers()
        spam = _spam_clients(samples, _cfg())
        self.assertGreaterEqual(len(spam), 6)
        self.assertEqual(judge_detail("A", samples, _cfg(), spam), "spam")

    def test_blocks_when_spam_is_removed_and_real_clients_still_fail(self):
        samples = []
        for i in range(4):
            samples.extend(_repeat("A", f"spam{i}", 5, success=False, recent=False))
        samples += _unique("A", 8, recent=False)
        samples += _unique("A", 8, recent=True)
        samples += _peers()
        blocks = decide_blocks(samples, _cfg())
        self.assertEqual([b.detail_id for b in blocks], ["A"])
        self.assertGreater(blocks[0].raw_issued, blocks[0].clean_issued)
        self.assertIsInstance(blocks[0], BlockDecision)

    def test_merchant_wide_drop_does_not_block(self):
        samples = _dead_card()
        # Other traders on the same merchant are just as empty, so the baseline is the merchant.
        samples += _unique("B", 12, trader="resdfe", recent=False)
        samples += _unique("C", 8, trader="resdfe", recent=True)
        samples += _unique("D", 15, trader="other", recent=False)
        samples += _unique("E", 12, trader="other", recent=True)
        self.assertEqual(decide_blocks(samples, _cfg()), [])

    def test_thin_card_is_ignored(self):
        samples = _unique("A", 10, recent=False) + _unique("A", 8, recent=True) + _peers()
        self.assertEqual(decide_blocks(samples, _cfg()), [])

    def test_inactive_card_is_ignored(self):
        samples = _unique("A", 24, recent=False, active=False) + _unique("A", 16, recent=True, active=False)
        samples += _peers()
        self.assertEqual(decide_blocks(samples, _cfg()), [])

    def test_max_pct_boundary(self):
        self.assertEqual(GuardConfig().max_pct, Decimal("5"))
