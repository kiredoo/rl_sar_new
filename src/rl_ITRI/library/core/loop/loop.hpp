#ifndef LOOP_H
#define LOOP_H

#include <atomic>
#include <chrono>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

#ifdef __linux__
#include <errno.h>
#include <pthread.h>
#include <time.h>
#endif

class LoopFunc
{
public:
    LoopFunc(const std::string &name,
             double period,
             std::function<void()> func,
             int bindCPU = -1,
             double phaseOffsetSec = 0.0)
        : _name(name),
          _period(period),
          _func(std::move(func)),
          _bindCPU(bindCPU),
          _phaseOffsetSec(phaseOffsetSec),
          _running(false)
    {
    }

    void start()
    {
        _running = true;
        log("[Loop Start] named: " + _name +
            ", period: " + formatMs(_period * 1000.0) + "(ms)" +
            ", phase offset: " + formatMs(_phaseOffsetSec * 1000.0) + "(ms)" +
            (_bindCPU != -1 ? ", run at cpu: " + std::to_string(_bindCPU) : ", cpu unspecified"));

        _thread = std::thread(&LoopFunc::loop, this);

        if (_bindCPU != -1)
        {
            setThreadAffinity(_thread.native_handle(), _bindCPU);
        }
    }

    void shutdown()
    {
        _running = false;

        if (_thread.joinable())
        {
            _thread.join();
        }

        log("[Loop End] named: " + _name);
    }

private:
    std::string _name;
    double _period;          // seconds
    std::function<void()> _func;
    int _bindCPU;
    double _phaseOffsetSec;  // seconds, applied before the first release
    std::atomic<bool> _running;
    std::thread _thread;

#ifdef __linux__
    static void addNs(struct timespec &ts, long long ns)
    {
        ts.tv_sec += static_cast<time_t>(ns / 1000000000LL);
        ts.tv_nsec += static_cast<long>(ns % 1000000000LL);
        if (ts.tv_nsec >= 1000000000L)
        {
            ts.tv_nsec -= 1000000000L;
            ts.tv_sec += 1;
        }
    }

    static bool isPast(const struct timespec &a, const struct timespec &b)
    {
        return (a.tv_sec > b.tv_sec) || (a.tv_sec == b.tv_sec && a.tv_nsec > b.tv_nsec);
    }

    static long long normalizeOffsetNs(double phaseOffsetSec, long long periodNs)
    {
        long long offsetNs = static_cast<long long>(std::llround(phaseOffsetSec * 1e9));
        if (offsetNs == 0)
        {
            return 0;
        }
        if (periodNs <= 0)
        {
            return offsetNs > 0 ? offsetNs : 0;
        }

        offsetNs %= periodNs;
        if (offsetNs < 0)
        {
            offsetNs += periodNs;
        }
        return offsetNs;
    }

    static void sleepUntilAbs(const struct timespec &deadline, const std::atomic<bool> &running)
    {
        int rc;
        do
        {
            rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &deadline, nullptr);
        } while (rc == EINTR && running.load());
    }
#endif

    void loop()
    {
        if (_period <= 0.0)
        {
            while (_running)
            {
                _func();
            }
            return;
        }

#ifdef __linux__
        const long long periodNs = static_cast<long long>(std::llround(_period * 1e9));
        const long long phaseOffsetNs = normalizeOffsetNs(_phaseOffsetSec, periodNs);

        struct timespec next;
        clock_gettime(CLOCK_MONOTONIC, &next);

        // Optional initial phase shift before the first release.
        if (phaseOffsetNs > 0)
        {
            addNs(next, phaseOffsetNs);
            if (_running)
            {
                sleepUntilAbs(next, _running);
            }
        }

        while (_running)
        {
            _func();

            // Move to the next absolute deadline.
            addNs(next, periodNs);

            // If the current cycle overran, skip missed slots and keep the phase/grid.
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            while (isPast(now, next))
            {
                addNs(next, periodNs);
            }

            if (!_running)
            {
                break;
            }

            sleepUntilAbs(next, _running);
        }
#else
        using clock = std::chrono::steady_clock;
        const auto period = std::chrono::duration_cast<clock::duration>(std::chrono::duration<double>(_period));
        const auto phaseOffset = std::chrono::duration_cast<clock::duration>(std::chrono::duration<double>(_phaseOffsetSec));

        auto next = clock::now();
        if (phaseOffset.count() > 0)
        {
            next += phaseOffset;
            std::this_thread::sleep_until(next);
        }

        while (_running)
        {
            _func();
            next += period;
            std::this_thread::sleep_until(next);
        }
#endif
    }

    static std::string formatMs(double valueMs)
    {
        std::ostringstream stream;
        stream << std::fixed << std::setprecision(3) << valueMs;
        return stream.str();
    }

    void log(const std::string &message)
    {
        static std::mutex logMutex;
        std::lock_guard<std::mutex> lock(logMutex);
        std::cout << message << std::endl;
    }

    void setThreadAffinity(std::thread::native_handle_type threadHandle, int cpuId)
    {
#ifdef __linux__
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(cpuId, &cpuset);
        if (pthread_setaffinity_np(threadHandle, sizeof(cpu_set_t), &cpuset) != 0)
        {
            std::ostringstream oss;
            oss << "Error setting thread affinity: CPU " << cpuId << " may not be valid or accessible.";
            throw std::runtime_error(oss.str());
        }
#else
        (void)threadHandle;
        (void)cpuId;
        throw std::runtime_error("Thread affinity not supported on this platform.");
#endif
    }
};

#endif // LOOP_H
