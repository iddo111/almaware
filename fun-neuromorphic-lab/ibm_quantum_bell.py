"""Submit a Bell-state experiment to a real IBM Quantum Open Plan QPU."""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2


def main() -> None:
    service = QiskitRuntimeService()
    backend = service.least_busy(
        operational=True,
        simulator=False,
        min_num_qubits=2,
    )

    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()

    pass_manager = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pass_manager.run(circuit)
    sampler = SamplerV2(mode=backend)
    job = sampler.run([isa_circuit], shots=1024)

    print(f"Backend: {backend.name}")
    print(f"Job ID:  {job.job_id()}")
    result = job.result()
    print(f"Counts:  {result[0].data.meas.get_counts()}")


if __name__ == "__main__":
    main()

