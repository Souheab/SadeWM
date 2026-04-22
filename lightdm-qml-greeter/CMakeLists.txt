cmake_minimum_required(VERSION 3.16)
project(sadewm-greeter LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt5 5.15 REQUIRED COMPONENTS Core Gui Qml Quick)
find_package(PkgConfig REQUIRED)
pkg_check_modules(LIGHTDM_QT REQUIRED IMPORTED_TARGET liblightdm-qt5-3)

add_executable(sadewm-greeter
    src/main.cpp
    src/greeterbridge.cpp
    src/greeterbridge.h
    qml/qml.qrc
)

target_link_libraries(sadewm-greeter
    PRIVATE
        Qt5::Core
        Qt5::Gui
        Qt5::Qml
        Qt5::Quick
        PkgConfig::LIGHTDM_QT
)

include(GNUInstallDirs)

install(TARGETS sadewm-greeter
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

# LightDM looks for greeter .desktop files in /usr/share/xgreeters
install(FILES data/sadewm-greeter.desktop
    DESTINATION ${CMAKE_INSTALL_DATADIR}/xgreeters)
