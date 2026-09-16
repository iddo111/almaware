> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Fun Neuromorphic + Quantum Lab

This is the runnable playground that was missing. The three local demonstrations use NumPy only—no Torch and no local model inference.

## Run the local demonstrations

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_local.ps1
```

Linux:

```bash
bash ./run_local.sh
```

Included:

- `memristor_crossbar_demo.py`: differential conductance crossbar, device noise, drift, and ADC quantization.
- `spiking_lif_demo.py`: leaky integrate-and-fire neurons with an ASCII spike raster.
- `reservoir_demo.py`: echo-state reservoir predicting a chaotic Mackey-Glass-style signal.
- `ibm_quantum_bell.py`: submits a Bell-state circuit to a real IBM QPU after IBM credentials are configured.

## Free real quantum hardware

Best first choice: IBM Quantum Open Plan. It currently offers up to 10 minutes of real QPU time per rolling 28-day window.

1. Create an account: https://quantum.cloud.ibm.com/
2. Create an Open Plan instance in the `us-east` region.
3. Generate an API key and copy the instance CRN.
4. Install the quantum dependencies:

```bash
python -m pip install -r requirements-quantum.txt
```

5. Save the credentials once, replacing both placeholders:

```python
from qiskit_ibm_runtime import QiskitRuntimeService
QiskitRuntimeService.save_account(
    token="YOUR_IBM_API_KEY",
    instance="YOUR_OPEN_PLAN_CRN",
    channel="ibm_quantum_platform",
    plans_preference=["open"],
    set_as_default=True,
)
```

6. Submit the real-hardware experiment:

```bash
python ibm_quantum_bell.py
```

The script uses job mode because IBM Open Plan does not permit sessions.

Second free real-hardware option: Quantum Inspire: https://www.quantum-inspire.com/

## Larger memristor/SNN frameworks

- IBM AIHWKit: https://github.com/IBM/aihwkit
- IBM AIHWKit-Lightning: https://github.com/IBM/aihwkit-lightning
- Sandia CrossSim: https://github.com/sandialabs/cross-sim
- snnTorch: https://snntorch.readthedocs.io/en/latest/tutorials/
- ReservoirPy: https://reservoirpy.readthedocs.io/en/latest/
- EBRAINS real BrainScaleS-2/SpiNNaker access: https://wiki.ebrains.eu/bin/view/Collabs/neuromorphic/Getting%20access/

