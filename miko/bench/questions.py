# -*- coding: utf-8 -*-
"""The question pool MIKO is asked.

Derived from Iddo's OWN research: the eight ruling files in the miko/ directory
(FINDINGS-2026-08-2x-*.md), each recording a real question he asked and the lenses
searched. The questions are in that register and in those eight domains, written in
English because the page corpus (fineweb-edu / CommonCrawl) is English.

This is a POOL. Which questions actually enter pairs.jsonl is decided by a MEASURED
coverage probe (probe_coverage.py) -- a question the corpus cannot answer at all is
dropped rather than kept as a row of zeros.

cluster ids map to his files:
  A giant-models-weak-machines   B collective-station     C ear-mouth-world
  D eran-chip                    E biofeedback-autogenic  F cycles
  G makers-lab-ai-computers      H physical-ai-substrates
"""

QUESTIONS = [
 # -- A - running big models on weak machines ---------------------------------
 ("A", "How does quantizing a neural network to fewer bits change its accuracy?"),
 ("A", "Why is memory bandwidth, not raw arithmetic speed, the bottleneck for large neural networks?"),
 ("A", "How can a computation be split across several machines running in parallel?"),
 ("A", "What is the difference between a CPU and a GPU for numerical work?"),
 ("A", "How does a neural network actually perform inference on new input?"),
 ("A", "What is knowledge distillation, where a small model learns from a large one?"),
 ("A", "How much memory does a deep learning model need, and what determines it?"),
 ("A", "What is cluster computing and how do nodes share a workload?"),
 ("A", "How does caching reduce the cost of repeated memory access?"),
 ("A", "What limits how fast a computer processor can run?"),
 ("A", "How do embedded systems run machine learning on low power devices?"),
 ("A", "What is floating point precision and how does reducing it affect a calculation?"),

 # -- B - the collective, cooperatives, solar ---------------------------------
 ("B", "How does a member-owned cooperative differ from a normal company in who controls it?"),
 ("B", "What is a credit union and how do its members share ownership?"),
 ("B", "How do community solar projects let a group of households share one installation?"),
 ("B", "How much electricity does a rooftop solar panel array generate over a year?"),
 ("B", "How do you size a battery bank for an off-grid solar system?"),
 ("B", "What is the history of the cooperative movement and its founding principles?"),
 ("B", "How do makerspaces and community workshops share expensive equipment among members?"),
 ("B", "How does a photovoltaic cell convert sunlight into electricity?"),
 ("B", "How do you calculate the electrical load of a building and the circuit it needs?"),
 ("B", "What is a housing cooperative and how do residents finance it together?"),
 ("B", "How do solar water heating systems work on a roof?"),
 ("B", "What governance structures let a large group make decisions democratically?"),

 # -- C - the ear, the mouth, the world ---------------------------------------
 ("C", "How does the cochlea separate sound into different frequencies?"),
 ("C", "What are formants and how do they distinguish one vowel from another?"),
 ("C", "How do the tongue, lips and jaw shape speech sounds?"),
 ("C", "What is the difference between a voiced and an unvoiced consonant?"),
 ("C", "How do hair cells in the inner ear turn vibration into nerve signals?"),
 ("C", "How does the human ear perceive pitch and loudness?"),
 ("C", "How do infants learn to produce the speech sounds of their language?"),
 ("C", "How does speech recognition software turn an audio signal into words?"),
 ("C", "What causes hearing loss and how does a hearing aid or cochlear implant help?"),
 ("C", "How does the vocal fold vibrate to produce the voice?"),
 ("C", "What is the frequency range of human hearing and why does it decline with age?"),
 ("C", "How is sound represented as a waveform and analysed into frequencies?"),

 # -- D - the ERAN chip -------------------------------------------------------
 ("D", "How are integrated circuits manufactured, from silicon wafer to packaged chip?"),
 ("D", "What is photolithography and why does wavelength limit the smallest feature?"),
 ("D", "How does a transistor work as a switch inside a computer chip?"),
 ("D", "What is an FPGA and how does it differ from a fixed-function chip?"),
 ("D", "How does a neuromorphic chip imitate neurons and synapses in hardware?"),
 ("D", "What is semiconductor yield and why does it fall as chips get larger?"),
 ("D", "How is silicon purified and grown into wafers for the semiconductor industry?"),
 ("D", "What are spiking neural networks and how do they differ from ordinary ones?"),
 ("D", "How does the law of transistor density growth work, and is it ending?"),
 ("D", "How do logic gates combine to build an arithmetic circuit?"),
 ("D", "What is doping in semiconductors and how does it create n-type and p-type material?"),
 ("D", "How much does it cost to design and fabricate a custom chip?"),

 # -- E - biofeedback and self-regulation -------------------------------------
 ("E", "What is autogenic training or relaxation training and how is a session conducted?"),
 ("E", "How is heart rate variability measured and what does it say about the nervous system?"),
 ("E", "Does biofeedback measurably reduce anxiety or stress in controlled studies?"),
 ("E", "How does EEG neurofeedback work and which brain rhythms does it train?"),
 ("E", "How does slow deep breathing affect heart rate and blood pressure?"),
 ("E", "Can flashing lights trigger a seizure, and at which flash rates?"),
 ("E", "What is the placebo effect and how do controlled trials account for it?"),
 ("E", "How does skin conductance change with emotional arousal?"),
 ("E", "What does an EEG measure and what do alpha and theta waves mean?"),
 ("E", "How does the autonomic nervous system balance sympathetic and parasympathetic activity?"),
 ("E", "Does meditation produce measurable physiological changes?"),
 ("E", "How does chronic stress affect the body's hormones and health?"),

 # -- F - cycles in nature and economics --------------------------------------
 ("F", "What causes the eleven year sunspot cycle and how regular is it?"),
 ("F", "What is El Nino and how does it change weather around the world?"),
 ("F", "How do you detect a periodic signal hidden in a noisy time series?"),
 ("F", "Why can a cycle appear in data that is actually random noise?"),
 ("F", "How do statisticians test whether an apparent pattern is real or chance?"),
 ("F", "Are there long waves in economic history, and what is the evidence?"),
 ("F", "How do predator and prey populations oscillate over time?"),
 ("F", "What are circadian rhythms and what biological clock drives them?"),
 ("F", "How does the agricultural season drive commodity prices through the year?"),
 ("F", "What is the multiple comparisons problem and how does it create false findings?"),
 ("F", "What drives the business cycle of expansion and recession?"),
 ("F", "How do ice cores and tree rings record past climate cycles?"),
 ("F", "What are the orbital cycles that pace the ice ages?"),
 ("F", "How does the lunar cycle drive the tides?"),

 # -- G - the makers lab that builds computers --------------------------------
 ("G", "How is a printed circuit board designed and manufactured?"),
 ("G", "What equipment and conditions does semiconductor fabrication require?"),
 ("G", "How can light or optics be used to perform computation?"),
 ("G", "What is fibre optics and how does light carry information through glass?"),
 ("G", "How do open source hardware projects license and share their designs?"),
 ("G", "What is a cleanroom and why does dust ruin microelectronics?"),
 ("G", "How is heat removed from densely packed electronics?"),
 ("G", "How does a 3D printer work and what materials can it print?"),
 ("G", "How does a laser cutter work and what can a workshop do with one?"),
 ("G", "How do you solder electronic components onto a board?"),
 ("G", "What is a microcontroller and how do you program one?"),
 ("G", "How does a CNC machine turn a digital design into a physical part?"),

 # -- H - physical substrates for computing -----------------------------------
 ("H", "What is a memristor and how does it remember its resistance?"),
 ("H", "How does an analog circuit compute with continuous voltages instead of bits?"),
 ("H", "What are the sources of noise and drift that limit analog measurement?"),
 ("H", "How do fungal networks in soil transmit signals and nutrients between plants?"),
 ("H", "How do plant roots sense and grow toward water?"),
 ("H", "How were analog computers built and what problems did they solve?"),
 ("H", "How does an electrochemical cell change its conductance?"),
 ("H", "How does a neuron transmit an electrical signal along its axon?"),
 ("H", "How do synapses change strength and store memory in the brain?"),
 ("H", "What is a slime mould and how does it solve maze and network problems?"),
 ("H", "How does DNA store information and could it be used for computing?"),
 ("H", "What is quantum computing and how does a qubit differ from a bit?"),
]

SIBLING = {"A": "D", "D": "G", "G": "H", "H": "F", "F": "E", "E": "C", "C": "B", "B": "A"}
