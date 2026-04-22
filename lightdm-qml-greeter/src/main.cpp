// SPDX-License-Identifier: MIT
//
// Entry point for the sadewm LightDM QML greeter.
//
// All user-facing logic lives in ``qml/Greeter.qml`` – this file is
// glue that stands up a QGuiApplication, wires QLightDM's Qt objects
// into the QML engine, and loads the root view.

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QScreen>
#include <QDebug>

#include <QLightDM/Greeter>
#include <QLightDM/UsersModel>
#include <QLightDM/SessionsModel>
#include <QLightDM/Power>

#include "greeterbridge.h"

int main(int argc, char *argv[])
{
    // LightDM traditionally launches greeters with no env that would
    // select a Qt platform; be explicit so we always get an X11 window.
    qputenv("QT_QPA_PLATFORM", QByteArrayLiteral("xcb"));

    QGuiApplication app(argc, argv);
    app.setApplicationName("sadewm-greeter");
    app.setOrganizationName("sadewm");

    QLightDM::Greeter greeter;
    const bool devMode = qEnvironmentVariableIsSet("SADEWM_GREETER_DEV");
    if (!devMode && !greeter.connectSync()) {
        qCritical() << "sadewm-greeter: failed to connect to the LightDM daemon";
        return 1;
    }
    if (devMode) {
        qWarning() << "sadewm-greeter: SADEWM_GREETER_DEV set - skipping "
                      "LightDM daemon connection (UI-only smoke test)";
    }

    QLightDM::UsersModel    usersModel;
    QLightDM::SessionsModel sessionsModel(QLightDM::SessionsModel::LocalSessions);
    QLightDM::PowerInterface power;

    GreeterBridge bridge(&greeter);

    // Register the Greeter type purely so QML can reach the
    // PromptType / MessageType enum values if it needs to.
    qmlRegisterUncreatableType<QLightDM::Greeter>(
        "QLightDM", 1, 0, "Greeter",
        "Use the provided 'greeter' context property");

    QQmlApplicationEngine engine;
    auto *ctx = engine.rootContext();
    ctx->setContextProperty("greeter",       &greeter);
    ctx->setContextProperty("bridge",        &bridge);
    ctx->setContextProperty("usersModel",    &usersModel);
    ctx->setContextProperty("sessionsModel", &sessionsModel);
    ctx->setContextProperty("power",         &power);

    engine.load(QUrl(QStringLiteral("qrc:/qml/Greeter.qml")));
    if (engine.rootObjects().isEmpty()) {
        qCritical() << "sadewm-greeter: failed to load QML";
        return 2;
    }

    // If the root object is a Window, ensure it covers the primary
    // screen – lightdm runs us as the only client on the display.
    auto *root = engine.rootObjects().first();
    if (auto *win = qobject_cast<QQuickWindow *>(root)) {
        auto *scr = QGuiApplication::primaryScreen();
        if (scr) {
            win->setGeometry(scr->geometry());
        }
    }

    return app.exec();
}
