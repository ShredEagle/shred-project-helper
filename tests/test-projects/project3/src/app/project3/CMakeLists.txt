set(TARGET_NAME project3)

set(${TARGET_NAME}_HEADERS
    utils.h
)

set(${TARGET_NAME}_SOURCE
    utils.cpp
)

source_group(TREE ${CMAKE_CURRENT_LIST_DIR}
             FILES ${${TARGET_NAME}_HEADERS}
                   ${${TARGET_NAME}_DOC}
)

add_library(${TARGET_NAME} 
    ${${TARGET_NAME}_HEADERS}
    ${${TARGET_NAME}_SOURCE}
)

add_library(sph::${TARGET_NAME} ALIAS ${TARGET_NAME})

cmc_target_current_include_directory(${TARGET_NAME})

set_target_properties(${TARGET_NAME} PROPERTIES
                      VERSION "${${TARGET_NAME}_VERSION}"
)

##
## Dependencies
##

cmc_find_dependencies()

##
## Install
##
install(TARGETS ${TARGET_NAME} EXPORT ${TARGET_NAME}Targets)

include(cmc-install)
# Install the header files
cmc_install_with_folders(DESTINATION include/${TARGET_NAME}/${TARGET_NAME}
                         FILES ${${TARGET_NAME}_HEADERS})
# Setup CMake package in both build and install trees
cmc_install_packageconfig(${TARGET_NAME} ${TARGET_NAME}Targets ${PROJECT_NAME}
                          FIND_FILE CMakeFinds.cmake.in
                          NAMESPACE sph::)
