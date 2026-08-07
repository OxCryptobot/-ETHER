# ETHER sprint: phaseG live Phase F re-measure (GPU, long)
# Run via:  .\scripts\host_runner.ps1 -Sprint phaseg_live_f -PushReport

# STEP: confirm_model
Select-String -Path .env -Pattern PRIMARY_MODEL

# STEP: phase_f_scripted
.\venv\Scripts\python.exe -m scripts.batch_phase_f --arm direct --mode scripted

# STEP: phase_f_live_direct
.\venv\Scripts\python.exe -m scripts.batch_phase_f --arm direct --mode live --max-steps 16 --timeout 500
