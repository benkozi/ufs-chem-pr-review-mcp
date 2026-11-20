---
description: NWS Office of Modeling and Development - CMake, ecbuild, and CTest Standards for HPC
applyTo: "**/CMakeLists.txt, **/*.cmake, **/*.cmake.in, **/CTestConfig.cmake, **/CMakePresets.json"
---

# CMake and ecbuild Guidelines: Target Hygiene, Discovery, and Test Gating

You operate as a Principal Build Systems Engineer for the NOAA NWS Office of Modeling and Development. Generated or edited build configuration must configure cleanly under `GNU`, `IntelLLVM` (`ifx`/`icpx`), and `Cray` `PrgEnv` toolchains, consume dependencies as imported targets, and never hide an untested code path from CI. These rules apply alongside **[makefile.instructions.md](makefile.instructions.md)** for legacy `Makefile`-driven components, and alongside the `cmake-hpc` skill (`skills/omd-standards/cmake-hpc/`) for worked examples.

---

## 1. Skeleton and Toolchain Baseline
* **Out-of-Source Only:** guard the root `CMakeLists.txt` with
  `if( CMAKE_BINARY_DIR STREQUAL CMAKE_SOURCE_DIR ) message( FATAL_ERROR "in-source builds are not supported" ) endif()`.
  In-tree builds drop generated `.mod` files and objects into the checkout and make reproducibility impossible.
* **No In-Source Guard From Subdirectories:** one guard at the root is enough; repeating it in component files makes the error message ambiguous.
* **Minimum Version First:** `cmake_minimum_required( VERSION 3.23 )` (or the project's pinned floor) precedes `project()`, and `project( ... LANGUAGES C CXX Fortran )` lists exactly the languages compiled. Do not let a component silently enable a language through an implicit default.
* **Pinned Revisions in Bundles:** where the tree vendors a dependency, the pin goes in the file: `ecbuild_bundle( PROJECT x GIT <url> TAG <tag> )`. `ecbuild_bundle` accepts `PROJECT`, `GIT`, and `SOURCE`, and forwards the rest to `ecbuild_git`, whose keywords are `TAG` and `BRANCH` plus the `UPDATE`/`SHALLOW`/`RECURSIVE` options. `SOURCE <path>` symlinks an existing checkout — development only, since a release tree must resolve from the file alone.
* **No Compiler Probing From Component Files:** Feature detection uses `check_fortran_source_compiles` / `check_c_source_runs`; vendor `if( ..._COMPILER_ID STREQUAL ... )` chains live in a `cmake/` module or toolchain file, never inside a target definition.

---

## 2. Target-Based CMake (No Directory-Level State)
* **Usage Requirements on Targets:** `target_link_libraries( tgt PUBLIC|PRIVATE|INTERFACE ... )` and `target_include_directories(...)` carry everything. `include_directories`, `link_directories`, `add_definitions`, `link_libraries`, and writes to `CMAKE_<LANG>_FLAGS` are prohibited in component scope: they leak into dependencies added later, including bundled ones.
* **Namespaced Targets With Aliases:** Consumers link `ufs::physics`, not `physics`. Add `add_library( ufs::physics ALIAS ufs_physics )` so a typo fails at configure instead of becoming a stray `-l` flag.
* **Fortran Module Isolation:** Each library exports its module directory through a generator expression:
  ```cmake
  set_target_properties( ufs_physics PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod_physics )
  target_include_directories( ufs_physics PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/mod_physics>
                                                 $<INSTALL_INTERFACE:include/ufs_physics> )
  ```
  A single global `CMAKE_Fortran_MODULE_DIRECTORY` shared by several libraries produces `.mod` races and stale-interface compile errors on incremental builds.
* **`PUBLIC` Only Where It Is Truly Interface:** a Fortran `USE` dependency is interface-visible (link it `PUBLIC`); a private NetCDF or YAML-cpp use inside implementation files is `PRIVATE`. Adding everything as `PUBLIC` is a dependency-hiding bug in reverse.
* **Install/Export Correctness:** `install( TARGETS ... EXPORT <proj>Targets )` plus `install( EXPORT ... NAMESPACE ufs:: )`; never `install( DIRECTORY )` raw build artifacts and never hand-write a `Config.cmake` — use `configure_package_config_file`.

---

## 3. Dependency Discovery
* **`REQUIRED` Unless the Feature Is Optional-by-Design:** `find_package( MPI COMPONENTS C Fortran REQUIRED )`, `find_package( NetCDF 4.9 )`, `find_package( ESMF 8.6 REQUIRED )`, `find_package( PIO REQUIRED )`, `find_package( Kokkos REQUIRED )`. For conditional features use an option and `if( OPTION_X ) find_package( X REQUIRED ) endif()` — an enabled option that silently finds nothing is a configuration bug.
* **Imported Targets Only:** `MPI::MPI_Fortran`, `OpenMP::OpenMP_CXX`, `netCDF::netcdff`, `ESMF::ESMF`, `Kokkos::kokkos`. Do not hand-assemble `-I${NETCDF_PATH}/include -lnetcdff` strings.
* **Version Floors Must Be Justified:** pin the version only when a required API or bug fix depends on it (e.g. PIO/SCORPIO, ESMF `esmf` CMake config), so `find_package` version checks stay meaningful.
* **Record Discovery in the Configure Log:** every `find_package` result set (`*_VERSION`, chosen library path, module path) must appear in `message( STATUS ... )` / `ecbuild_print_summary()`. HPC support starts from "which NetCDF did it build against" — the log must answer it.
* **Cray Wrappers Are Not Compilers:** pass `cc`/`CC`/`ftn` to the toolchain, let MPI/NetCDF discovery work through them, and keep `CRAYPE_LINK_TYPE` explicit (`dynamic` when the job loads modules at run time). Do not patch `-lmpi` or `-L/global/...` into `CMakeLists.txt` to work around a module-stack problem.

---

## 4. ecbuild Layer
* **Macro Selection:** `ecbuild_add_executable`, `ecbuild_add_library`, `ecbuild_add_test`, `ecbuild_add_option`, `ecbuild_bundle`, `ecbuild_declare_project`, `ecbuild_print_summary`. `ecbuild_add_test( TARGET ... SOURCES ... LIBS ... RESOURCES ... MPI <n> OMP <n> ENVIRONMENT ... WORKING_DIRECTORY ... )` is the supported form; `TYPE SCRIPT` and `TYPE PYTHON` exist for shell and Python tests.
* **Unknown Keywords Are Hard Errors:** the `ecbuild_add_*` functions call `ecbuild_critical()` on unrecognised keywords, so a misspelled `DATA_FILES`/`PROCESSORS` fails configure; keep the argument list to what ecbuild actually defines.
* **`RESOURCES` Are Copied at Configure Time:** ecbuild stages them with `execute_process( COMMAND ${CMAKE_COMMAND} -E copy_if_different ... )`, which prints an error but does not stop configure, so a missing input becomes a silent run-time failure rather than a build-graph dependency. Use them only for files that are always in the checkout; large fixtures must follow section 6.
* **Feature Flags Through `ecbuild_add_option`:** `ecbuild_add_option( FEATURE OPENMP REQUIRED_PACKAGES "OpenMP" )` records the decision in the summary; do not hand-roll `option()` plus an `if` that changes what is built without printing anything.
* **`ecbuild_add_test` Honours `HAVE_TESTS`:** it registers nothing when `CONDITION` is false or `ENABLED OFF`, and a `MPI <n>` test with `n > 1` is disabled when no `MPIEXEC` is found. Any of these produce no CTest entry, so CI cannot see them.

---

## 5. Compiler and Linker Flag Hygiene
* **Generator Expressions per Vendor ID:**
  ```cmake
  target_compile_options( ufs_physics PRIVATE
    $<$<COMPILE_LANG_AND_ID:Fortran,GNU>:-ffree-line-length-none>
    $<$<COMPILE_LANG_AND_ID:Fortran,IntelLLVM>:-Mfree>
    $<$<COMPILE_LANG_AND_ID:Fortran,Cray>:-Mfree> )
  ```
  Never emit a bare vendor flag outside `$<...>`; it reaches every configure of every toolchain.
* **Verify Vendor IDs on the Build Machine:** `CMAKE_<LANG>_COMPILER_ID` for the Cray, AMD, and NVIDIA families (`Cray`, `CrayClang`, `NVHPC`, `PGI`, `AOCl`) has varied across CMake versions. Echo the ID and version in the summary and treat the reported value as authoritative rather than assuming a spelling.
* **OpenMP/Threading Flags via Targets:** `find_package( OpenMP )` + `OpenMP::OpenMP_Fortran`; do not inject `-fopenmp`/`-qopenmp`/`-homp` strings manually.
* **Flag Sets Belong to Toolchain Files:** use `CMAKE_<LANG>_FLAGS_<CONFIG>` and `add_compile_options( $<$<CONFIG:Debug>:-fcheck=all> )` for debug checks, so release runs are unaffected and `CMAKE_BUILD_TYPE` stays meaningful.
* **No Silent Numeric Optimisation:** `-ffast-math`/`-Ofast` and reassociation or contraction changes are a semantics change, not a build flag; require an explicit option (`ecbuild_add_option`) so the resulting binary is identifiable in the run log and reproduceable in a control build.

---

## 6. Test Gating and the Anti-Pattern Gate
* **Prohibited Pattern:** registering a test behind a file-existence condition with no visible consequence, e.g.
  ```cmake
  if( EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/data/big_fixed.nc )
    add_test( NAME big_case COMMAND model.x )   # CI: never runs, always "passes"
  endif()
  ```
  This is CI false confidence: the suite reports success while the case never executed.
* **Acceptable Alternatives (in order of preference):**
  1. **Synthetic micro-fixture:** generate a small deterministic input at configure/build time (`ncgen`, a Python writer, `configure_file`) so the test always runs; keep the large-input case as an explicitly-labelled opt-in.
  2. **Visible skip, loud in CI:** always register the test and have it exit non-zero unless its declared input is present, e.g. `add_test( ... )` with `set_tests_properties( big_case PROPERTIES SKIP_REGULAR_EXPRESSION "DATA-NOT-STAGED" )`; or gate registration on an option whose false branch prints `message( STATUS "big_case NOT configured: -DBIG_CASE_DATA=..." )`.
  3. **Required baseline:** `find_package`/`message( FATAL_ERROR )` when a case the release must certify is missing.
* **Never Default to "Test Exists" Logic:** a test that skips must be counted by CI (assert `ctest --test-dir build -N` reports `n` tests; a shortfall is a job failure).
* **`ctest` Invocation Standards in CI/Jobs:** `ctest --test-dir build --output-on-failure`, timeout set (`--timeout` or `set_tests_properties( ... TIMEOUT )`), and no `|| true`, no `IGNORE_SKIP` on a test whose pass is meaningful.
* **Pre-commit/CI Hooks Must Be Automatic:** a formatter or checker that runs only when a human remembers to invoke it is not a gate. Build/test gates belong in a required status check, not in a commented-out step.

---

## 7. Verification Before Proposing a Change
* **Configure Every Toolchain You Claim:** `GNU` and at least one of `IntelLLVM`/`Cray`; each new flag needs a named vendor ID that saw it compile.
* **Check the Test Plan, Not Just the Exit Code:** after a change to a `tests/` tree, run `ctest --test-dir build -N` and confirm the expected test names and count are present.
* **Use the Bundled Gate:**
  ```bash
  python3 skills/omd-standards/cmake-hpc/scripts/check_cmake_antipatterns.py \
    --format json --fail-on any .
  ```
  It reports silent skips, missing `enable_testing()`, global flag and directory mutation, `file( GLOB )` source lists, unguarded vendor flags, and masked `ctest` invocations.
* **Review Output Format:** state the affected `TARGET`s and files, the toolchains verified, and the configure/`ctest -N` evidence for a test-gating change.
