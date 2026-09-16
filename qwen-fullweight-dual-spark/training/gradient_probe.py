"""DGX-only runtime gradient coverage hooks.

This module imports Torch and must never be imported on the Windows PC.
Static validation parses it as text.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch


class GradientCoverageProbe:
    def __init__(self, model, accelerator):
        self.accelerator = accelerator
        self.names: list[str] = []
        self.numel: list[int] = []
        self.seen_nonzero: list[bool] = []
        self.seen_nonfinite: list[bool] = []
        self._handles = []
        self.router_seen: dict[str, torch.Tensor] = {}
        self.router_num_experts: dict[str, int] = {}

        for index, (name, parameter) in enumerate(model.named_parameters()):
            if not parameter.requires_grad:
                raise RuntimeError(f"frozen parameter after distributed prepare: {name}")
            self.names.append(name)
            self.numel.append(int(getattr(parameter, "ds_numel", parameter.numel())))
            self.seen_nonzero.append(False)
            self.seen_nonfinite.append(False)
            self._handles.append(parameter.register_hook(self._hook(index)))

        if not self.names:
            raise RuntimeError("distributed wrapper exposed no trainable parameters")
        inventory = "\n".join(
            f"{name}\0{numel}" for name, numel in zip(self.names, self.numel, strict=True)
        )
        self.parameter_inventory_sha256 = hashlib.sha256(
            inventory.encode("utf-8")
        ).hexdigest()

        unwrapped = accelerator.unwrap_model(model)
        router_class_names = {
            "Qwen3MoeTopKRouter",
            "Qwen3_5MoeTopKRouter",
        }
        for module_name, module in unwrapped.named_modules():
            if module.__class__.__name__ not in router_class_names:
                continue
            num_experts = int(module.num_experts)
            self.router_num_experts[module_name] = num_experts
            self.router_seen[module_name] = torch.zeros(
                num_experts, dtype=torch.int64, device=accelerator.device
            )
            self._handles.append(
                module.register_forward_hook(
                    self._router_hook(module_name, num_experts)
                )
            )

    def _hook(self, index: int):
        def mark(gradient):
            if gradient is None:
                return gradient
            finite = torch.isfinite(gradient)
            flags = torch.stack(
                (
                    finite.all(),
                    torch.where(finite, gradient.ne(0), False).any(),
                )
            ).to(dtype=torch.uint8, device="cpu")
            finite_all, finite_nonzero = [bool(value) for value in flags.tolist()]
            if not finite_all:
                self.seen_nonfinite[index] = True
            if finite_nonzero:
                self.seen_nonzero[index] = True
            return gradient

        return mark

    def _router_hook(self, module_name: str, num_experts: int):
        def mark_routes(_module, _inputs, output):
            if not isinstance(output, tuple) or len(output) < 3:
                raise RuntimeError(
                    f"unexpected MoE router output for coverage: {module_name}"
                )
            selected_experts = output[-1].detach().reshape(-1).to(dtype=torch.int64)
            counts = torch.bincount(selected_experts, minlength=num_experts)
            self.router_seen[module_name].add_(counts[:num_experts])

        return mark_routes

    def write(self, output_path: Path, run_id: str, optimizer_steps: int) -> None:
        digest = torch.tensor(
            list(bytes.fromhex(self.parameter_inventory_sha256)),
            dtype=torch.uint8,
            device=self.accelerator.device,
        )
        gathered_digests = self.accelerator.gather(digest).reshape(-1, 32)
        if gathered_digests.shape[0] != self.accelerator.num_processes:
            raise RuntimeError("parameter inventory digest rank count mismatch")
        inventories_match = gathered_digests.eq(gathered_digests[0]).all()
        if not bool(inventories_match.item()):
            raise RuntimeError(
                "parameter name/order/size inventory differs across ranks; "
                "positional gradient reduction is unsafe"
            )

        local_nonzero = torch.tensor(
            self.seen_nonzero, dtype=torch.uint8, device=self.accelerator.device
        )
        local_nonfinite = torch.tensor(
            self.seen_nonfinite, dtype=torch.uint8, device=self.accelerator.device
        )
        global_seen = self.accelerator.reduce(
            local_nonzero, reduction="sum"
        ).gt(0)
        global_nonfinite = self.accelerator.reduce(
            local_nonfinite, reduction="sum"
        ).gt(0)
        router_rows = []
        for module_name in sorted(self.router_seen):
            route_observations = self.accelerator.reduce(
                self.router_seen[module_name], reduction="sum"
            )
            observation_list = [
                int(value) for value in route_observations.cpu().tolist()
            ]
            routed_list = [value > 0 for value in observation_list]
            router_rows.append(
                {
                    "module": module_name,
                    "num_experts": self.router_num_experts[module_name],
                    "expert_route_observations": observation_list,
                    "experts_routed": routed_list,
                    "covered_count": sum(routed_list),
                    "observation_note": (
                        "Forward-hook observations are coverage evidence, not exact "
                        "token counts; activation recomputation can repeat them."
                    ),
                }
            )
        if self.accelerator.is_main_process:
            rows = [
                {
                    "name": name,
                    "numel": numel,
                    "requires_grad": True,
                    "nonzero_gradient_seen": bool(seen),
                    "nonfinite_gradient_seen": bool(nonfinite),
                }
                for name, numel, seen, nonfinite in zip(
                    self.names,
                    self.numel,
                    global_seen.cpu().tolist(),
                    global_nonfinite.cpu().tolist(),
                    strict=True,
                )
            ]
            payload = {
                "schema_version": 3,
                "run_id": run_id,
                "optimizer_steps": optimizer_steps,
                "world_size": self.accelerator.num_processes,
                "parameter_inventory_sha256": self.parameter_inventory_sha256,
                "parameters": rows,
                "moe_router_coverage": router_rows,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def close(self) -> None:
        for handle in self._handles:
            handle.remove()
