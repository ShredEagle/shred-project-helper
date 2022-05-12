cmake_minimum_required(VERSION 3.16)

# NOTE: Cannot set `VERSION ${BUILD_VERSION}` here, because the conanuser_config
# file defining the variable has not yet been included
project(Project2)

include(cmake/include.cmake)

cmc_include_conan_configuration()

option(BUILD_Project2_DEVMODE
       "Build Grapito application in development mode, not for public release."
       FALSE)

add_subdirectory(src)
