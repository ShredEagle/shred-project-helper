

# Conan automatically generated toolchain file
# DO NOT EDIT MANUALLY, it will be overwritten

# Avoid including toolchain file several times (bad if appending to variables like
#   CMAKE_CXX_FLAGS. See https://github.com/android/ndk/issues/323
include_guard()

if(CMAKE_TOOLCHAIN_FILE)
    message("Using Conan toolchain: ${CMAKE_TOOLCHAIN_FILE}.")
endif()





set(CMAKE_BUILD_TYPE "Debug" CACHE STRING "Choose the type of build." FORCE)


set(CONAN_CXX_FLAGS "${CONAN_CXX_FLAGS} -m64")
set(CONAN_C_FLAGS "${CONAN_C_FLAGS} -m64")
set(CONAN_SHARED_LINKER_FLAGS "${CONAN_SHARED_LINKER_FLAGS} -m64")
set(CONAN_EXE_LINKER_FLAGS "${CONAN_EXE_LINKER_FLAGS} -m64")

set(CONAN_CXX_FLAGS "${CONAN_CXX_FLAGS} -stdlib=libstdc++")


message(STATUS "Conan toolchain: C++ Standard 20 with extensions OFF}")
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_CXX_FLAGS_INIT "${CMAKE_CXX_FLAGS_INIT} ${CONAN_CXX_FLAGS}")
set(CMAKE_C_FLAGS_INIT "${CMAKE_C_FLAGS_INIT} ${CONAN_C_FLAGS}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${CMAKE_SHARED_LINKER_FLAGS_INIT} ${CONAN_SHARED_LINKER_FLAGS}")
set(CMAKE_EXE_LINKER_FLAGS_INIT "${CMAKE_EXE_LINKER_FLAGS_INIT} ${CONAN_EXE_LINKER_FLAGS}")

get_property( _CMAKE_IN_TRY_COMPILE GLOBAL PROPERTY IN_TRY_COMPILE )
if(_CMAKE_IN_TRY_COMPILE)
    message(STATUS "Running toolchain IN_TRY_COMPILE")
    return()
endif()

set(CMAKE_FIND_PACKAGE_PREFER_CONFIG ON)
# To support the generators based on find_package()
set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_LIST_DIR} "/home/franz/.conan/data/boost/1.77.0/_/_/package/6d519bf8cffee115e1a51e65d3be2760752538c8/" "/home/franz/.conan/data/zlib/1.2.11/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" "/home/franz/.conan/data/bzip2/1.0.8/_/_/package/4b8e817c304dca09c454779755c305c8386492dc/" "/home/franz/.conan/data/bzip2/1.0.8/_/_/package/4b8e817c304dca09c454779755c305c8386492dc/lib/cmake" "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" ${CMAKE_MODULE_PATH})
set(CMAKE_PREFIX_PATH ${CMAKE_CURRENT_LIST_DIR} "/home/franz/.conan/data/boost/1.77.0/_/_/package/6d519bf8cffee115e1a51e65d3be2760752538c8/" "/home/franz/.conan/data/zlib/1.2.11/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" "/home/franz/.conan/data/bzip2/1.0.8/_/_/package/4b8e817c304dca09c454779755c305c8386492dc/" "/home/franz/.conan/data/bzip2/1.0.8/_/_/package/4b8e817c304dca09c454779755c305c8386492dc/lib/cmake" "/home/franz/.conan/data/libbacktrace/cci.20210118/_/_/package/0cac844812c2c06353def85537a0768d93e5455d/" ${CMAKE_PREFIX_PATH})

# To support cross building to iOS, watchOS and tvOS where CMake looks for config files
# only in the system frameworks unless you declare the XXX_DIR variables




message(STATUS "Conan toolchain: Setting BUILD_SHARED_LIBS = OFF")
set(BUILD_SHARED_LIBS OFF)

# Variables
# Variables  per configuration


# Preprocessor definitions
# Preprocessor definitions per configuration
