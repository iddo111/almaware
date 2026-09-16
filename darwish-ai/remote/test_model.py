# test_model.py — Task 5 gate: shapes, finite loss, param count in 150M-350M.
import torch

from model import DarwishLM, loss_fn


def main():
    torch.manual_seed(0)
    model = DarwishLM()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"params: {n_params/1e6:.1f}M")
    assert 150e6 <= n_params <= 350e6, "param count out of the not-too-big range"

    tokens = torch.randint(0, 1024, (2, 9, 300))
    logits, gist = model(tokens)
    assert logits.shape == (2, 9, 300, 1024), logits.shape
    assert gist.shape == (2, 300, 1024), gist.shape

    loss, parts = loss_fn(model, tokens)
    assert torch.isfinite(loss), loss
    print(f"loss ok: {float(loss):.3f} (ce={parts['ce']:.3f} gist={parts['gist']:.3f})")
    print("TEST-MODEL: PASS")


if __name__ == "__main__":
    main()
