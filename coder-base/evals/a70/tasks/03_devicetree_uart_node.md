# Task 3 — write a device-tree node: the console UART

**Level:** medium/hard. This is the actual, minimal "write a device tree
fragment" exercise a real bring-up engineer does first: without a working
console, every later debugging step gets harder, so bringing up the serial
console is normally step one after the board boots at all.

## Prompt to give the model

> The Samsung Galaxy A70 uses a Qualcomm SM6150 (Snapdragon 675) SoC. Its
> console UART is one of the SoC's GENI/QUP serial engines (the same IP
> block family used across Snapdragon 660/670/675/730 mainline device
> trees). Write the `arch/arm64/boot/dts/qcom/` device-tree node for this
> console UART, suitable for inclusion in a board-level `.dts` alongside a
> hypothetical `sm6150.dtsi`. Use realistic register/interrupt placeholder
> values if you do not know the real ones, but get the **binding shape**
> right: compatible string, clocks, pinctrl, status.

## Grading rubric (structural, regex-based — see honesty note below)

The submission is a device-tree source fragment (`.dts`/`.dtsi` text, one or
more nodes). `grader.py devicetree <submission.dts>` checks, purely
structurally:

| # | Check | Why required |
|---|---|---|
| 1 | Braces balance (`{`/`}` count equal) and every property line ends `;` | Minimal syntactic sanity — a real `dtc` compile is the strong version of this check (see below) |
| 2 | A node whose `compatible` property contains `"qcom,geni-uart"` **or** `"qcom,geni-debug-uart"` | These are the real upstream compatible strings for this IP block family (used, for example, in the sdm660-mainline and sdm845 upstream device trees for their console/debug UARTs) |
| 3 | An `interrupts` property is present | Every real UART node needs one |
| 4 | A `clocks` property with **at least one** phandle reference (`<&gcc ...>` or `<&rpmhcc ...>` shape), and a matching `clock-names` | Console UARTs on this SoC family are clocked from the GCC (Global Clock Controller); a node with no clock reference cannot be real |
| 5 | `pinctrl-names` includes `"default"`, and a matching `pinctrl-0 = <&...>` phandle | UART RX/TX pins must be muxed through TLMM pinctrl or the pins never carry the signal |
| 6 | `status = "okay"` **somewhere** (either on this node directly, or the submission explicitly notes that the SoC-level node ships `status = "disabled"` and the *board* `.dts` must override it to `"okay"`) | Standard qcom mainline convention: SoC `.dtsi` nodes default disabled; only the board file enables what's actually wired up |

**Score = checks passed / 6. Pass = 5/6 or 6/6.**

### Honesty note on this grader

This machine has no `dtc` (device tree compiler) installed — checked
directly (`which dtc` / `where dtc`: not found). A real acceptance test
would compile the fragment with `dtc -I dts -O dtb` against a real
`sm6150.dtsi` include chain and confirm zero errors/warnings; that is a
**stronger, more falsifiable check than this regex-based one**, and it
should replace this checker before anyone trusts a "pass" here as proof the
syntax is actually valid DTS, only that it has the right *shape*. Anyone
running this eval on a Linux box with `dtc` available should compile-check
real submissions, not just trust this proxy.
