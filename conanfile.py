from conans import ConanFile, tools
from conan.tools.cmake import CMakeDeps, CMake, CMakeToolchain
from conans.tools import SystemPackageTool
from conan.errors import ConanException
import os
import shutil
from pathlib import Path, PurePosixPath
import subprocess

required_conan_version = ">=1.60.0"


class XeusZmqConan(ConanFile):
    python_requires = "bundleutils/0.1@lkeb/stable"
    python_requires_extend = "bundleutils.BundleUtils"

    name = "xeus-python"
    version = "0.15.12"
    license = "MIT"
    author = "B. van Lew b.van_lew@lumc.nl"
    url = "https://github.com/jupyter-xeus/xeus-python.git"
    description = """xeus-python is a Jupyter kernel for Python based on the native implementation of the Jupyter protocol xeus."""
    topics = ("python", "jupyter", "python", "xeus")
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "testing": [True, False], 'merge_package': [True, False]}
    default_options = {"shared": True, "testing": False, 'merge_package': False}
    generators = "CMakeDeps"
    exports = "cmake/*"

    # Note: 
    # nlohmann_json pybind11 and pybind11_json are all header only
    # An alternative build configuration might simply be to have these
    # as submodules of this repo.
    requires = (
        "nlohmann_json/3.11.3",  # resolve conflict between pybind11_json & xeus-xmq by overriding
        "xtl/0.7.5",
        "xeus-zmq/1.1.1@lkeb/stable",
        "pybind11/2.11.1",
        "pybind11_json/0.2.11"
    )

    def init(self):
        # use the buntilutils to record the 
        # original source directory
        self._save_git_path()

    def source(self):
        try:
            self.run(f"git clone {self.url}")
        except ConanException as e:
            print(e)
        os.chdir("./xeus-python")
        try:
            self.run(f"git checkout tags/{self.version}")
        except ConanException as e:
            print(e)
        ## for CMP0091 policy set xeus CMake version to at least 3.15
        xeuspythoncmake = os.path.join(self.source_folder, "xeus-python", "CMakeLists.txt")
        tools.replace_in_file(xeuspythoncmake, "cmake_minimum_required(VERSION 3.4.3)", "cmake_minimum_required(VERSION 3.21)")
        tools.replace_in_file(xeuspythoncmake, "find_package(PythonInterp ${PythonLibsNew_FIND_VERSION} REQUIRED", "find_package(Python ${PythonLibsNew_FIND_VERSION} COMPONENTS Interpreter Development REQUIRED")
        tools.replace_in_file(xeuspythoncmake, "ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}", "ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}/$<CONFIG>")
        tools.replace_in_file(xeuspythoncmake, "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}", "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/$<CONFIG>")
        tools.replace_in_file(xeuspythoncmake, "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}", "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}/$<CONFIG>")
        # force linking with release also in debug
        tools.replace_in_file(xeuspythoncmake, "target_link_libraries(${target_name} PRIVATE ${PYTHON_LIBRARIES})", "target_link_libraries(${target_name} PRIVATE ${Python_LIBRARY_RELEASE})")
        install_text = """
add_dependencies(xpython xeus-python-static xeus-python)

add_custom_command(TARGET xpython POST_BUILD
    COMMAND "${CMAKE_COMMAND}"
    --install ${CMAKE_CURRENT_BINARY_DIR}
    --config $<CONFIG>
    --prefix ${CMAKE_CURRENT_BINARY_DIR}/install/$<CONFIG>
)


"""
        with open(xeuspythoncmake, "a") as cmakefile:
            cmakefile.write(install_text)

        os.chdir("..")

    def _get_tc(self):
        """Generate the CMake configuration using
        multi-config generators on all platforms, as follows:

        Windows - defaults to Visual Studio
        Macos - XCode
        Linux - Ninja Multi-Config

        CMake needs to be at least 3.17 for Ninja Multi-Config

        Returns:
            CMakeToolchain: a configured toolchain object
        """
        generator = None
        if self.settings.os == "Macos":
            generator = "Xcode"

        if self.settings.os == "Linux":
            generator = "Ninja Multi-Config"

        tc = CMakeToolchain(self, generator=generator)
        tc.variables["BUILD_TESTING"] = "ON" if self.options.testing else "OFF"
        tc.variables["BUILD_SHARED_LIBS"] = "ON" if self.options.shared else "OFF"
        tc.variables["CMAKE_PREFIX_PATH"] = Path(self.build_folder).as_posix()
        tc.variables["CMAKE_VERBOSE_MAKEFILE"] = "ON"

        if self.settings.os == "Linux":
            tc.variables["CMAKE_CONFIGURATION_TYPES"] = "Debug;Release;RelWithDebInfo"

        if self.settings.os == "Macos":
            proc = subprocess.run(
                "brew --prefix libomp", shell=True, capture_output=True
            )
            prefix_path = f"{proc.stdout.decode('UTF-8').strip()}"
            tc.variables["OpenMP_ROOT"] = prefix_path

        tc.variables["PythonLibsNew_FIND_VERSION"] = "3.11"

        xeuspath = Path(self.deps_cpp_info["xeus"].rootpath).as_posix()
        tc.variables["xeus_ROOT"] = xeuspath
        print(f"********xeus_root: {xeuspath}**********")
        xeuszmqpath = Path(self.deps_cpp_info["xeus-zmq"].rootpath).as_posix()
        tc.variables["xeus-zmq_ROOT"] = xeuszmqpath
        print(f"********xeus-zmq_root: {xeuszmqpath}**********")
        zeromqpath = Path(xeuszmqpath, "CMake")
        print(f"********zeromq_path: {zeromqpath}**********")
        tc.variables["ZeroMQ_ROOT"] = zeromqpath.as_posix()
        # zeromqpath = Path(self.deps_cpp_info["zeromq"].rootpath).as_posix()
        # print(f"********zeromq_path: {zeromqpath}**********")
        # tc.variables["zeromq_ROOT"] = zeromqpath
        # cppzmqpath = Path(Path(self.deps_cpp_info["cppzmq"].rootpath), 'lib', 'cmake').as_posix()
        # tc.variables["cppzmq_ROOT"] = cppzmqpath
        pybindpath = Path(self.deps_cpp_info["pybind11"].rootpath).as_posix()
        tc.variables["pybind11_ROOT"] = pybindpath
        pybindpath = Path(self.deps_cpp_info["pybind11_json"].rootpath).as_posix()
        tc.variables["pybind11_json_ROOT"] = pybindpath


        # Build the test executable for reference
        tc.variables["XPYT_BUILD_XPYTHON_EXECUTABLE"] = "ON"
        return tc
    
    def configure(self):
        # Force the zmq to use the shared lib
        self.options["zeromq"].shared = True

    #def layout(self):
        # Cause the libs and bin to be output to separate subdirs
        # based on build configuration.
        self.cpp.package.libdirs = ["lib"]
        self.cpp.package.bindirs = ["bin"]

    def system_requirements(self):
        if self.settings.os == "Macos":
            installer = SystemPackageTool()
            installer.install("libomp")
            # Make the brew OpenMP findable with a symlink
            proc = subprocess.run("brew --prefix libomp",  shell=True, capture_output=True)
            subprocess.run(f"ln {proc.stdout.decode('UTF-8').strip()}/lib/libomp.dylib /usr/local/lib/libomp.dylib", shell=True)

    def generate(self):
        # 
        deps = CMakeDeps(self)
        deps.generate()
        tc = self._get_tc()
        tc.generate()
        #  {Path(self.deps_cpp_info['cppzmq'].rootpath, 'include').as_posix()}
        #  {Path(self.deps_cpp_info['zeromq'].rootpath, 'include').as_posix()}
        with open("conan_toolchain.cmake", "a") as toolchain:
            toolchain.write(
                fr"""
include_directories(
    {Path(self.deps_cpp_info['nlohmann_json'].rootpath, 'include').as_posix()}
    {Path(self.deps_cpp_info['xeus'].rootpath, 'include').as_posix()}
    {Path(self.deps_cpp_info['xtl'].rootpath, 'include').as_posix()}
    {Path(self.deps_cpp_info['pybind11'].rootpath, 'include').as_posix()}
    {Path(self.deps_cpp_info['pybind11_json'].rootpath, 'include').as_posix()}
)
            """
            )

    def _configure_cmake(self):
        cmake = CMake(self)
        cmake.verbose = True
        build_folder = os.path.join(self.build_folder, "xeus-python")
        print(f"Source folder {Path(self.source_folder).as_posix()}")
        try:
            cmake.configure(build_script_folder="xeus-python") #, cli_args=["--trace"])
        except ConanException as e:
            print(f"Exception: {e} from cmake invocation: \n Completing configure")

        return cmake

    def build(self):
        self._save_package_id()
        # Build both release and debug for dual packaging
        # cmake_release = self._configure_cmake()
        # cmake_release.build(cli_args=["--verbose"])
        # cmake_release.install()

        cmake = self._configure_cmake()

        cmake.build(build_type="Debug")
        cmake.install(build_type="Debug")

        cmake = self._configure_cmake()

        cmake.build(build_type="Release")
        cmake.install(build_type="Release")

    # This is to make combined packages 
    #def package_id(self):
    #    del self.info.settings.build_type
    #    if self.settings.compiler == "Visual Studio":
    #        del self.info.settings.compiler.runtime

    # Package contains its own cmake config file
    def package_info(self):
        self.cpp_info.set_property("skip_deps_file", True)
        self.cpp_info.set_property("cmake_config_file", True)

    def _pkg_bin(self, build_type):
        src_dir = f"{self.build_folder}/{build_type}"
        dst_lib = f"lib/{build_type}"
        dst_bin = f"bin/{build_type}"

        self.copy("*.exe", src=src_dir, dst=dst_bin, keep_path=False)
        self.copy("*.dll", src=src_dir, dst=dst_bin, keep_path=False)
        self.copy("*.so", src=src_dir, dst=dst_lib, keep_path=False)
        self.copy("*.dylib", src=src_dir, dst=dst_lib, keep_path=False)
        self.copy("*.a", src=src_dir, dst=dst_lib, keep_path=False)
        self.copy("*.lib", src=src_dir, dst=dst_lib, keep_path=False)
        print(f"Build type {build_type}")
        if ((build_type == "Debug") or (build_type == "RelWithDebInfo")) and (
            self.settings.compiler == "Visual Studio"
        ):
            # the debug info
            print("Adding pdb files for Windows debug")
            self.copy("*.pdb", src=src_dir, dst=dst_lib, keep_path=False)

    def package(self):
        # cleanup excess installs - this is a kludge TODO fix cmake
        print("cleanup")
        for child in Path(self.package_folder, "lib").iterdir():
            if child.is_file():
                child.unlink()
        print("end cleanup")
        self.copy("*.h", src="xeus-python/src/cpp", dst="include", keep_path=True)
        self.copy("*.hpp", src="xeus-python/src/cpp", dst="include", keep_path=True)

        self._pkg_bin(self.settings.build_type)

        # This allow the merging op multiple build_types into a single package
        self._merge_from = ["Debug"]
        self._merge_to = "Release" 
        self._merge_packages()
