using UnityEngine;

public class TrajectoryVisualizer : MonoBehaviour
{
    [Header("Match these to Figure8Controller")]
    public float radius = 2.0f;
    public float height = 2.0f; // Must match the drone's height
    public int resolution = 100;
    
    private LineRenderer lineRenderer;

    void Start()
    {
        lineRenderer = GetComponent<LineRenderer>();
        if (lineRenderer == null)
        {
            lineRenderer = gameObject.AddComponent<LineRenderer>();
        }

        // Fix the pink color by assigning a default material if missing
        if (lineRenderer.material == null)
        {
            lineRenderer.material = new Material(Shader.Find("Sprites/Default"));
        }
        
        lineRenderer.startColor = Color.red;
        lineRenderer.endColor = Color.red;
        lineRenderer.startWidth = 0.05f;
        lineRenderer.endWidth = 0.05f;
        lineRenderer.positionCount = resolution + 1;
        lineRenderer.useWorldSpace = true;
        lineRenderer.loop = true;

        // Generate Points (Exact same math as Figure8Controller)
        Vector3 center = transform.position;
        center.y = height;

        Vector3[] points = new Vector3[resolution + 1];
        for (int i = 0; i <= resolution; i++)
        {
            float t = (float)i / resolution * Mathf.PI * 2f;
            float x = radius * Mathf.Sin(t);
            float z = radius * Mathf.Sin(t) * Mathf.Cos(t);
            
            points[i] = center + new Vector3(x, 0, z);
        }

        lineRenderer.SetPositions(points);
    }
}