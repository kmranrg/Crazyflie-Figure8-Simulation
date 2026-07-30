using UnityEngine;
using System.Collections.Generic;

public class Figure8Controller : MonoBehaviour
{
    [Header("Trajectory Parameters")]
    public float speed = 0.5f;
    public float radius = 2.0f;
    public float height = 1.5f;
    
    [Header("APF Controller Gains")]
    public float attractiveGain = 3.0f;      // Pull toward trajectory
    public float repulsiveGain = 8.0f;       // Push away from person
    public float tangentialGain = 2.0f;      // Sideways avoidance
    public float velocityDamping = 0.95f;    // Smooth velocity changes
    
    [Header("Avoidance Settings")]
    public Transform userHead;
    public float avoidanceRadius = 2.0f;     // Start planning avoidance
    public float safetyBuffer = 1.0f;        // Minimum safe distance
    public float smoothReturnDistance = 2.5f; // Distance to start smooth return
    
    [Header("Sub-Goal Settings")]
    public float subGoalLookahead = 1.0f;    // Distance along trajectory to look
    public float maxDeviationAngle = 60f;    // Max angle to deviate from path
    
    [Header("Smooth Return Settings")]
    public float returnBlendingRate = 0.02f; // How quickly to blend back (0-1)
    public int bezierResolution = 20;        // Points for Bezier curve
    
    private Rigidbody rb;
    private float time;
    private Vector3 centerOffset;
    
    // State management
    private bool isAvoiding = false;
    private bool isReturning = false;
    private Vector3 avoidanceStartPosition;
    private Vector3 currentSubGoal;
    private float avoidanceBlendFactor = 0f;
    private List<Vector3> returnTrajectory;
    private int currentReturnPoint = 0;
    
    // Potential field components
    private Vector3 attractiveForce;
    private Vector3 repulsiveForce;
    private Vector3 tangentialForce;
    
    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.useGravity = true;
        rb.linearDamping = 0.5f;  // Add damping for smoothness
        centerOffset = transform.position;
        centerOffset.y = height;
        returnTrajectory = new List<Vector3>();
    }
    
    void FixedUpdate()
    {
        if (userHead == null) return;
        
        // Calculate distance to user
        Vector3 toUser = userHead.position - transform.position;
        float distanceToUser = toUser.magnitude;
        
        // State machine for avoidance behavior
        if (distanceToUser < avoidanceRadius && !isReturning)
        {
            // ENTER AVOIDANCE MODE
            if (!isAvoiding)
            {
                isAvoiding = true;
                avoidanceStartPosition = transform.position;
                avoidanceBlendFactor = 0f;
                Debug.Log("Entering avoidance mode");
            }
            
            ApplyArtificialPotentialField(toUser, distanceToUser);
        }
        else if (distanceToUser > smoothReturnDistance && isAvoiding)
        {
            // ENTER SMOOTH RETURN MODE
            if (!isReturning)
            {
                isReturning = true;
                isAvoiding = false;
                GenerateSmoothReturnTrajectory();
                currentReturnPoint = 0;
                Debug.Log("Entering smooth return mode");
            }
            
            FollowSmoothReturnTrajectory();
        }
        else if (isReturning && currentReturnPoint >= returnTrajectory.Count)
        {
            // EXIT RETURN MODE - Back to normal tracking
            isReturning = false;
            avoidanceBlendFactor = 0f;
            Debug.Log("Resumed normal trajectory tracking");
        }
        else
        {
            // NORMAL TRAJECTORY TRACKING
            ApplyTrajectoryForce();
            isAvoiding = false;
            isReturning = false;
        }
        
        // Apply velocity damping for smoothness
        rb.linearVelocity *= velocityDamping;
    }
    
    void ApplyArtificialPotentialField(Vector3 toUser, float distanceToUser)
    {
        // 1. Calculate attractive force toward nominal trajectory
        attractiveForce = CalculateAttractiveForce();
        
        // 2. Calculate repulsive force from person
        repulsiveForce = CalculateRepulsiveForce(toUser, distanceToUser);
        
        // 3. Calculate tangential force (perpendicular to avoid oscillation)
        tangentialForce = CalculateTangentialForce(toUser);
        
        // 4. Blend forces based on proximity to person
        float dangerFactor = Mathf.Clamp01((avoidanceRadius - distanceToUser) / avoidanceRadius);
        avoidanceBlendFactor = Mathf.Lerp(avoidanceBlendFactor, dangerFactor, Time.fixedDeltaTime * 2f);
        
        // 5. Combine forces with dynamic weighting
        Vector3 totalForce = Vector3.zero;
        
        // Weight repulsive force more when closer
        totalForce += repulsiveForce * Mathf.Lerp(0f, repulsiveGain, avoidanceBlendFactor);
        totalForce += tangentialForce * Mathf.Lerp(0f, tangentialGain, avoidanceBlendFactor);
        
        // Always maintain some attraction to trajectory (prevents getting stuck)
        totalForce += attractiveForce * Mathf.Lerp(attractiveGain * 0.3f, attractiveGain * 0.1f, avoidanceBlendFactor);
        
        // Apply force with smoothing
        rb.AddForce(totalForce, ForceMode.Force);
        
        // Update sub-goal for visualization/debugging
        currentSubGoal = transform.position + (totalForce.normalized * subGoalLookahead);
    }
    
    Vector3 CalculateAttractiveForce()
    {
        // Find nearest point on Figure-8 trajectory
        Vector3 nearestPoint = FindNearestPointOnTrajectory();
        Vector3 toTrajectory = nearestPoint - transform.position;
        
        // Linear attractive potential (simpler and more stable)
        return toTrajectory * attractiveGain;
    }
    
    Vector3 CalculateRepulsiveForce(Vector3 toUser, float distanceToUser)
    {
        // Inverse quadratic repulsive potential (smooth falloff)
        if (distanceToUser > avoidanceRadius) return Vector3.zero;
        
        float safeDistance = avoidanceRadius - safetyBuffer;
        if (distanceToUser < safeDistance)
        {
            // Strong repulsion when too close
            float repulsiveMagnitude = repulsiveGain * (1f / distanceToUser - 1f / avoidanceRadius);
            return toUser.normalized * repulsiveMagnitude * 10f;
        }
        
        // Gentle repulsion in warning zone
        float falloff = Mathf.Pow((avoidanceRadius - distanceToUser) / safeDistance, 2);
        return toUser.normalized * repulsiveGain * falloff;
    }
    
    Vector3 CalculateTangentialForce(Vector3 toUser)
    {
        // Calculate perpendicular direction to avoid oscillation
        Vector3 toTrajectoryCenter = centerOffset - transform.position;
        Vector3 tangentialDir = Vector3.Cross(toUser.normalized, Vector3.up).normalized;
        
        // Choose direction that moves away from trajectory center (natural avoidance)
        if (Vector3.Dot(tangentialDir, toTrajectoryCenter) > 0)
            tangentialDir = -tangentialDir;
        
        // Add upward component for 3D avoidance
        tangentialDir += Vector3.up * 0.3f;
        tangentialDir.Normalize();
        
        return tangentialDir * tangentialGain;
    }
    
    Vector3 FindNearestPointOnTrajectory()
    {
        // Sample trajectory to find nearest point
        Vector3 nearestPoint = Vector3.zero;
        float minDistance = float.MaxValue;
        
        int samples = 50;
        for (int i = 0; i < samples; i++)
        {
            float t = (float)i / samples * Mathf.PI * 2f;
            float x = radius * Mathf.Sin(t);
            float z = radius * Mathf.Sin(t) * Mathf.Cos(t);
            Vector3 point = centerOffset + new Vector3(x, 0, z);
            
            float distance = Vector3.Distance(transform.position, point);
            if (distance < minDistance)
            {
                minDistance = distance;
                nearestPoint = point;
            }
        }
        
        return nearestPoint;
    }
    
    void GenerateSmoothReturnTrajectory()
    {
        // Generate Bezier curve from current position back to trajectory
        returnTrajectory.Clear();
        
        Vector3 startPos = transform.position;
        Vector3 endPos = FindNearestPointOnTrajectory();
        
        // Calculate control points for smooth Bezier curve
        Vector3 midPoint = (startPos + endPos) * 0.5f;
        Vector3 direction = (endPos - startPos).normalized;
        
        // Add upward arc for smooth return
        Vector3 controlPoint1 = startPos + direction * Vector3.Distance(startPos, endPos) * 0.5f + Vector3.up * 0.5f;
        Vector3 controlPoint2 = endPos - direction * Vector3.Distance(startPos, endPos) * 0.3f + Vector3.up * 0.3f;
        
        // Generate Bezier curve points
        for (int i = 0; i <= bezierResolution; i++)
        {
            float t = (float)i / bezierResolution;
            Vector3 point = CalculateCubicBezier(t, startPos, controlPoint1, controlPoint2, endPos);
            returnTrajectory.Add(point);
        }
        
        Debug.Log($"Generated return trajectory with {returnTrajectory.Count} points");
    }
    
    Vector3 CalculateCubicBezier(float t, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3)
    {
        // Cubic Bezier curve formula
        float u = 1f - t;
        float tt = t * t;
        float uu = u * u;
        float uuu = uu * u;
        float ttt = tt * t;
        
        return p0 * uuu + 3f * p1 * uu * t + 3f * p2 * u * tt + p3 * ttt;
    }
    
    void FollowSmoothReturnTrajectory()
    {
        if (currentReturnPoint >= returnTrajectory.Count) return;
        
        // Get next waypoint
        Vector3 targetPoint = returnTrajectory[currentReturnPoint];
        Vector3 toWaypoint = targetPoint - transform.position;
        float distanceToWaypoint = toWaypoint.magnitude;
        
        // Move toward waypoint with PD control
        if (distanceToWaypoint > 0.1f)
        {
            Vector3 velocityError = targetPoint - transform.position - rb.linearVelocity * 0.5f;
            Vector3 force = velocityError * attractiveGain * 0.5f; // Gentler during return
            rb.AddForce(force, ForceMode.Force);
        }
        else
        {
            // Waypoint reached, move to next
            currentReturnPoint++;
        }
    }
    
    void ApplyTrajectoryForce()
    {
        // Standard trajectory tracking (same as before)
        time += speed * Time.fixedDeltaTime;
        float x = radius * Mathf.Sin(time);
        float z = radius * Mathf.Sin(time) * Mathf.Cos(time);
        Vector3 targetPosition = centerOffset + new Vector3(x, 0, z);
        
        Vector3 positionError = targetPosition - transform.position;
        Vector3 velocityError = -rb.linearVelocity;
        
        Vector3 controlForce = (positionError * attractiveGain) + (velocityError * 2.0f);
        rb.AddForce(controlForce, ForceMode.Force);
    }
    
    // Debug visualization
    void OnDrawGizmos()
    {
        if (userHead == null) return;
        
        // Draw avoidance radius
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireSphere(transform.position, avoidanceRadius);
        
        // Draw safety buffer
        Gizmos.color = Color.red;
        Gizmos.DrawWireSphere(userHead.position, safetyBuffer);
        
        // Draw sub-goal
        if (isAvoiding)
        {
            Gizmos.color = Color.green;
            Gizmos.DrawSphere(currentSubGoal, 0.1f);
            Gizmos.DrawLine(transform.position, currentSubGoal);
        }
        
        // Draw return trajectory
        if (isReturning && returnTrajectory.Count > 0)
        {
            Gizmos.color = Color.cyan;
            for (int i = 0; i < returnTrajectory.Count - 1; i++)
            {
                Gizmos.DrawLine(returnTrajectory[i], returnTrajectory[i + 1]);
            }
        }
    }
}