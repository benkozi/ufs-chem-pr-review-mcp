# NOAA RDHPCS & HPC Workload Manager Guidelines

*Source: NOAA-EMC/omd-skills (`skills/hpc-skills/slurm/`, `skills/hpc-skills/pbs/`, and RDHPCS system skills)*

## 1. Slurm & PBS Batch Script Standards

- **Directive Consistency**:
  - The resources requested in `#SBATCH` or `#PBS` directives must match what the script actually launches:
    - `--ntasks` / `-n` must match `srun` or `mpirun` rank counts.
    - `--cpus-per-task` / `-c` must match `OMP_NUM_THREADS`.
    - Always set `export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?set by Slurm}"`.
- **Environment & Module Discipline**:
  - Always `module purge` before `module load`.
  - Pin explicit compiler and library module versions rather than loading default/floating modules.
  - Rely on scheduler environment variables (`$SLURM_JOB_ID`, `$SLURM_SUBMIT_DIR`, `$PBS_JOBID`) rather than hardcoded paths.
- **Exit Status Propagation**:
  - Always capture and propagate the application's exit status (`status=$?; exit "$status"`) so a failed rank does not report `COMPLETED` to the scheduler.

---

## 2. NOAA RDHPCS Shared Fleet Policies

Rules applicable across Hera, Ursa, Orion, Hercules, Gaea, PPAN, and Mercury:

- **Login Nodes are Non-Compute**:
  - Shared login/front-end nodes are for editing, job submission, and minor transfers only.
  - No compiling, no threaded runs, and no heavy I/O on login nodes; use interactive debug allocations (`salloc`) or service partitions (`service`, `u1-service`, `dtn`).
- **Never Run Jobs in `/home`**:
  - Do not run jobs against files in `/home`, including through symlinks that point into home. Running jobs against home degrades the metadata server for all users. Run on `/scratch`.
- **Scratch is Non-Backed-Up**:
  - Scratch file systems (`/scratch1`, `/scratch2`, `/scratch3-4`, `/gpfs5/purged`) are temporary and not backed up.
  - Durable outputs must be staged to project storage or archived.
- **HPSS & Long-Term Archiving**:
  - HPSS retains only **one single copy** of a file with no backup or recovery after deletion.
  - Compute nodes cannot reach HPSS; run transfers on front-end/service nodes with `module load hpss` (`module load hsi`).
  - Keep single files under 1 TB (files over 3 TB fail). Bundle small files with `htar`.

---

## 3. RDHPCS QOS Reference (Hera & Ursa)

| QOS | Max Walltime | Limits & Billing | Guidance |
| :--- | :--- | :--- | :--- |
| `batch` | 8 hours | Billing TRES: 1 | Default QOS for projects with active allocation. |
| `urgent` | 8 hours | Billing TRES: 2 | 1 job per project pending/running. Drops FairShare at 2x rate. |
| `debug` | 30 minutes | Billing TRES: 1.25 | Max 2 jobs per user. Fast turnaround for testing, not production. |
| `long` | 16 hours | Billing TRES: 1 | Standard priority for 8 to 16 hour workloads. |
| `windfall` | 8 hours | Billing TRES: 0 | Charges 0 allocation; does not affect FairShare. Lowest priority. |
| `gpu` / `gpuwf` | 168h / 48h | GPU nodes | Dedicated GPU allocations on Ursa. |
